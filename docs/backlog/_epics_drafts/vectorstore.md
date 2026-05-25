## File: docs/backlog/vectorstore.md

**Scope:** Embedding storage, similarity search, and vector namespace lifecycle for `backend/vectorstore/` and its factory wiring in `backend/api/dependencies.py` / `backend/agent/coordinator.py`. Covers adapter parity (in-memory, Qdrant) plus roadmap adapters (pgvector, Weaviate) listed in `docs/architecture.md` §3 (line 119) and §5.2 (line 137); namespace lifecycle (create/drop/reshape), filtered + hybrid search, snapshot/backup tooling, sharding/replication for prod load, source-document cascade completeness, tenant-scoped collections, dimension governance with embeddings, health probes for worker readiness, observability (latency, recall@k), and per-provider cost tracking. Excludes embedding generation (owned by `embeddings.md`) and RAG query orchestration (owned by `rag.md`).

Source-of-truth audit of `backend/vectorstore/` against `docs/architecture.md` §3 (container catalog), §5.2 (vectorstore row), §6 (KB cascade + dual-graph), §7 (data plane), §14.2 (future capabilities) and the live spec `2026-05-19-vectorstore-1-0-design.md`. The 1.0 release surface is shipped; remaining epics cover roadmap adapters, operations, and cross-cutting concerns not in 1.0 scope.

Done and intentionally **not** carried forward as epics:
- Full 1.0 synchronous service contract — `index`, `search`, `batch_search`, `get_record`, `count`, `delete_record`, `delete_knowledge_base` (`backend/vectorstore/protocols.py:21-37`, `backend/vectorstore/service.py:51-214`).
- Qdrant adapter full protocol implementation with lazy collection create, deterministic point IDs, payload-encoded records, filter translation (`backend/vectorstore/adapters/qdrant_adapter.py:111-416`).
- In-memory adapter parity for namespace lifecycle, filters, dimension validation (`backend/vectorstore/adapters/in_memory.py:14-127`).
- `delete_by_source_document` shipped on protocol, in-memory, Qdrant, and service (`backend/vectorstore/adapters/protocols.py:40-44`, `in_memory.py:111-127`, `qdrant_adapter.py:261-299`, `service.py:216-232`).
- Index audit artifact persistence to object store at `knowledgebases/{kb_id}/vector_index/{request_id}.json` (`backend/vectorstore/service.py:234-264`).
- `VectorsIndexedEvent` + `VectorsDeletedEvent` publication (`backend/vectorstore/service.py:121-133, 208-213`).
- Architecture guard test that Qdrant SDK does not leak outside the adapter (`backend/tests/vectorstore/test_architecture.py`).

---

## Epic 1: Expand live Qdrant integration coverage beyond round-trip and namespace delete

**Gap:** Only two `@pytest.mark.integration` tests exist against a live Qdrant — `test_qdrant_vector_store_round_trip_search` and `test_qdrant_vector_store_live_delete_namespace` (`backend/tests/vectorstore/test_qdrant_adapter.py:598, 650`). The 1.0 spec §"Testing And Release Gates" required live coverage of *all* protocol methods; `get_record`, `count_records`, `delete_record`, `delete_by_source_document`, filter translation, dimension-mismatch rejection, and missing-collection behavior have only fake-client coverage. Real Qdrant payload encoding, point-ID uuid5 collisions, and filter semantics (especially the float `gte/lte` range trick at `qdrant_adapter.py:443-446`) are not validated end-to-end.

**Outcome:** every adapter protocol method has a `@pytest.mark.integration` test gated on `QDRANT_URL`; CI profile runs the integration suite against the docker-compose Qdrant; live tests share a per-test ephemeral collection and clean up on teardown.

---

## Epic 2: Add pgvector adapter against the existing protocol

**Gap:** Architecture §3 (line 119) and §5.2 (line 137) list pgvector as a roadmap backend. `VectorStoreConfig.backend: Literal["qdrant", "in_memory"]` (`backend/config/schema.py:109`) rejects `pgvector`; `api/dependencies.py` `get_vectorstore_service` has no pgvector resolution path. CLAUDE.md "Hard Rules" §2 forbids widening the literal until protocol + factory wiring + contract tests land. A Postgres-resident vector store would also let smaller deployments avoid running Qdrant when `database/` already provisions Postgres.

**Outcome:** `PgvectorVectorStore` implements the full `VectorStoreProtocol` against `pgvector` extension; reuses `database.ConnectionProvider`; shared contract test suite (lazy collection create, upsert, search w/ filters, get, count, delete record, delete namespace, delete-by-source-document, dimension mismatch, missing namespace); factory wiring extended; `Literal` widened to `"pgvector"` only after the contract suite passes; live tests under `pytest -m integration` when `POSTGRES_URL` is set.

---

## Epic 3: Add Weaviate adapter against the existing protocol

**Gap:** Same architectural call-out as pgvector — Weaviate is listed in §3 (line 119) and §5.2 (line 137) as a roadmap adapter. No `WeaviateVectorStore`, no `weaviate` optional dependency in `backend/pyproject.toml`, no factory branch. Weaviate's class-per-tenant model and hybrid-search story is a distinct shape from Qdrant's collections — the shared contract suite from Epic 2 needs to cover both.

**Outcome:** `WeaviateVectorStore` implements `VectorStoreProtocol`; class/collection naming maps from `knowledge_base_id`; `weaviate-client` added as `[weaviate]` optional extra; factory wiring extended; passes the shared contract suite from Epic 2; live tests under `pytest -m integration` when `WEAVIATE_URL` is set.

---

## Epic 4: Add snapshot and backup tooling for vector namespaces

**Gap:** No snapshot/restore exists in `backend/vectorstore/` (grep for `snapshot|backup` returns nothing). The complete-backlog design spec §5 cites "vectorstore.04 Qdrant snapshot scheduling" as the canonical example story (`docs/superpowers/specs/2026-05-24-complete-backlog-design.md:211`). Qdrant has native snapshot APIs (`POST /collections/{c}/snapshots`) and pgvector backups go through `pg_dump`; the in-memory adapter has no persistence. Without snapshots, a corrupted KB index cannot be restored without re-running ingestion + embeddings, which can be hours of compute.

**Outcome:** `VectorSnapshotProtocol` extension surface (`create_snapshot(kb_id) -> ObjectStoreKey`, `restore_snapshot(kb_id, key, mode=replace|merge)`, `list_snapshots(kb_id)`); per-adapter implementation (Qdrant native snapshot → object store upload; pgvector via SQL dump; in-memory JSON round-trip for tests); periodic snapshot job scheduled from `agent/coordinator.py`; checksum + dimension round-trip test; cross-edge to `_infra.md` (snapshot storage location, retention policy) and `_observability.md` (snapshot job health).

---

## Epic 5: Add explicit namespace lifecycle management with dimension reshape

**Gap:** Namespace creation is implicit (lazy on first `upsert_records` — `qdrant_adapter.py:142-147`, `in_memory.py:42-43`). There is no `create_namespace(kb_id, dimension)` to provision a collection before any vectors arrive (so a probe can verify the collection is ready). There is no `reshape_namespace(kb_id, new_dimension)` for the embedder-swap workflow — today a dimension change raises `VectorDimensionMismatchError` (`qdrant_adapter.py:317-322`, `in_memory.py:36-40`) and the only recovery is `delete_knowledge_base` followed by full re-index, which is destructive and silently drops audit history. The 1.0 spec deferred this; once Epic 6 (embeddings model versioning) lands, reshape becomes a hard requirement.

**Outcome:** explicit `create_namespace(kb_id, dimension)` and `describe_namespace(kb_id) -> NamespaceInfo` on protocol; `reshape_namespace(kb_id, new_dimension, source: blue_green)` migrates to a new collection while the old one serves reads, then atomically swaps; both adapters implement; tests cover create-before-write, double-create idempotency, and blue/green swap rollback.

---

## Epic 6: Add sharding and replication knobs for production Qdrant load

**Gap:** `QdrantVectorStore._ensure_collection` creates collections with `VectorParams(size=dimension, distance=self._distance)` only (`qdrant_adapter.py:325-331`) — no `shard_number`, no `replication_factor`, no `write_consistency_factor`, no `on_disk_payload`. `VectorStoreConfig` (`backend/config/schema.py:106-113`) exposes `backend`, `uri`, `dimensions`, `distance_metric` only. For production claims-stream volumes (millions of vectors per KB) the single-shard default will hit throughput and storage ceilings; for HA the lack of replication is a single-point-of-failure. Cross-edge to `_infra.md` (Qdrant cluster topology).

**Outcome:** `VectorStoreConfig` gains `shard_number`, `replication_factor`, `write_consistency_factor`, `on_disk_payload`, `hnsw_config` (M, ef_construct); `create_collection` passes these through; per-KB override surface for large vs small KBs; load-test budget documented (e.g., ≥10k vectors/sec upsert, p95 search < 100ms at 1M vectors); pgvector/Weaviate equivalents recorded.

---

## Epic 7: Add range, list, and compound metadata filters

**Gap:** Service-level and adapter-level filters accept `dict[str, MetadataValue]` (scalar equality only — `backend/vectorstore/models.py:11`, `service_models.py:95`). The 1.0 spec §"Metadata And Filtering" explicitly defers list filters, range filters, and faceting. Qdrant supports `Range`, `MatchAny`, `should`/`must_not` natively; the float-equality hack (`qdrant_adapter.py:443-446`) is already a range filter under the hood. Without these, monitoring/RAG can't ask "vectors with `claim_amount > 5000` in `state in [TN, KY]`" — they have to over-fetch then filter in Python.

**Outcome:** extended `MetadataFilter` model supporting `eq`, `range(gte/lte)`, `in_list`, compound `must`/`should`/`must_not`; adapter translations for Qdrant (native), pgvector (`WHERE` clause), Weaviate (`where` builder), in-memory (Python predicate); back-compat shim accepts the existing `dict` shape; service request models extended; contract suite covers all combinator shapes.

---

## Epic 8: Add hybrid search (vector + keyword) on adapters that support it

**Gap:** Only dense vector search is exposed — `VectorSearchRequest` has `query_vector` but no `query_text` (`backend/vectorstore/service_models.py:89-101`). Qdrant supports BM25 / sparse vectors via `Query` payload; Weaviate supports `hybrid()` natively; pgvector pairs with `tsvector`. The 1.0 spec defers hybrid; the architecture endgame (§7 RAG pipeline) calls for keyword + vector retrieval to handle exact-match cases (NPI numbers, ICD codes) where dense embeddings score poorly. Cross-edge to `rag.md`.

**Outcome:** `VectorSearchRequest.query_text: str | None` + `hybrid: HybridConfig` (`alpha`, `keyword_field`); adapter capability flag (`supports_hybrid: bool`) on protocol; Qdrant + Weaviate implement, pgvector implements via `tsvector` join, in-memory simulates with substring boost; RAG context builder learns to set `query_text=request.user_query`; tests cover dense-only, sparse-only, and hybrid retrieval rank shifts.

---

## Epic 9: Validate `delete_by_source_document` edge cases and pipeline integration

**Gap:** The method shipped on all three layers (service, protocol, both adapters — `backend/vectorstore/service.py:216-232`, `adapters/protocols.py:40-44`, `in_memory.py:111-127`, `qdrant_adapter.py:261-299`) but architecture §7 (line 780) notes the document-delete endpoint *does not* call it: "Graph/vector cascade cleanup via `delete_by_source_document` is called on the re-upload (changed-content) path; it is not yet wired to the document-delete endpoint." Edge cases unverified: missing `SOURCE_DOCUMENT_ID_KEY` in metadata (silent no-op vs error), multiple source-doc IDs sharing a record, very large doc deletes (Qdrant scroll vs single delete-by-filter), and concurrency with in-flight indexing of the same doc. No event is published on this delete (unlike `delete_knowledge_base` which publishes `VectorsDeletedEvent`).

**Outcome:** `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` wired to call `VectorService.delete_by_source_document`; published `VectorsDeletedEvent` (or new `VectorsDocumentDeletedEvent`) for downstream observability; edge-case tests for missing metadata key, multi-doc records, large deletes (>10k vectors per doc); concurrency test that interleaves index + delete of the same doc; cross-edge to `api.md` (wiring) and `monitoring.md` (event consumers).

---

## Epic 10: Add tenant-scoped collections / namespaces

**Gap:** Collection naming is `chili_{knowledge_base_id}` (`backend/vectorstore/adapters/qdrant_adapter.py:415`) with no tenant prefix. `VectorStoreProtocol` operations take only `knowledge_base_id`; there is no `tenant_id` parameter, no default-deny filter, and no per-tenant collection-list isolation. Architecture §14.2 lists multi-tenancy isolation as Medium priority; §7 (line 1291) calls for "separate vector store namespaces" per tenant. Today, two tenants writing to the same `knowledge_base_id` value would collide silently. Cross-edge to `_multitenancy.md`, `_security.md`.

**Outcome:** decision recorded between (a) `tenant_id` prefix in collection name (`chili_{tenant_id}_{kb_id}`), (b) per-tenant Qdrant cluster, (c) Qdrant native multi-tenancy via payload-based isolation; `VectorStoreProtocol` operations accept `tenant_id` (or rely on contextvar set by auth middleware); cross-tenant query attempts default-deny; tests cover tenant isolation across all CRUD/search ops; pgvector/Weaviate analogue chosen.

---

## Epic 11: Cross-validate embedder dimension against vector collection on boot and on swap

**Gap:** `VectorStoreConfig.dimensions` (`backend/config/schema.py:111`) is declared in config but the cross-validation with `EmbeddingsConfig.dimensions` is explicitly deferred — the schema comment at `schema.py:113` reads "Cross-validation with EmbeddingsConfig.dimensions is deferred to E1-S06." `QdrantVectorStore._validate_query_dimension` (`qdrant_adapter.py:310-314`) compares the *query* vector against `self._config.dimensions`, not against the embedder's actual output dimension; an embedder/config mismatch only surfaces on first search. There is no preflight that asks the embedder its real dimension and asserts the collection matches. Cross-edge to `embeddings.md` epic 7 (dimension governance).

**Outcome:** boot-time preflight in `create_vector_service` (or a startup hook) that asks the bound embedder for its dimension and asserts equality with `VectorStoreConfig.dimensions` and with any existing collection's stored dimension; config loader warns when `EmbeddingsConfig.dimensions != VectorStoreConfig.dimensions`; on embedder swap, the reshape workflow (Epic 5) is the supported migration path.

---

## Epic 12: Add vector-store health probes for worker and API readiness

**Gap:** No `ping()` / `health_check()` on `VectorStoreProtocol` or `VectorServiceProtocol`; no readiness endpoint in `backend/api/routers/` references vectorstore. The Qdrant adapter constructs a `QdrantClient` at init (`qdrant_adapter.py:127-128`) but never pings it — a misconfigured `uri` or down Qdrant only surfaces on first upsert/search. The agent worker (`backend/agent/coordinator.py:1706`) also has no startup probe. Cross-edge to `agent.md` (worker readiness), `_observability.md` (probe surface).

**Outcome:** `health_check() -> VectorStoreHealth` on protocol (status, latency_ms, backend, collections_present); adapter implementations call backend-native ping (Qdrant `cluster_status`, pgvector `SELECT 1`, Weaviate `meta()`); API readiness endpoint includes vectorstore status; worker delays consuming events until probe passes; tests cover the probe with both healthy and unreachable backends.

---

## Epic 13: Add vectorstore observability — query latency, batch metrics, recall@k tracking

**Gap:** `VectorService` and adapters emit no metrics, traces, or structured logs beyond a single warning when audit persistence fails (`backend/vectorstore/service.py:261-264`). No counters for `index_call_count`, `search_call_count`, `vectors_indexed_total`, `vectors_deleted_total`; no histogram for `vector_search_duration_ms`; no trace spans around adapter calls. The architecture spec §14.2 calls for full observability; today operators cannot answer "what's our p95 search latency on the claims KB?" The complete-backlog spec example story (vectorstore.04 in §5) implicitly assumes this telemetry exists. Recall@k regression tracking is impossible without ground-truth eval harness. Cross-edge to `_observability.md`, `rag.md` (RAG recall is a downstream property).

**Outcome:** module metrics (`chili_vectorstore_*`) for op count/duration/error, batch size distribution, vectors per call; OpenTelemetry spans around adapter calls (`upsert_records`, `search`, namespace ops); structured audit log on writes/deletes (KB id, counts — no embedding payloads logged); recall@k evaluation harness using a held-out ground-truth set per KB, scheduled via `agent/coordinator.py`; dashboard panels declared in `_observability.md`.

---

## Epic 14: Add per-provider cost tracking and quota enforcement

**Gap:** No cost surface in `backend/vectorstore/` — vector storage cost (per-GB Qdrant Cloud, per-row pgvector storage, Weaviate Cloud per-object), search-API call cost (Weaviate Cloud, Qdrant Cloud), and snapshot/egress cost are all invisible. Architecture §14.2 calls out tenant-level resource attribution as a Medium-priority capability. Without it, multi-tenant cost allocation and quota enforcement (e.g., "tenant X exceeded 1M vectors") are impossible. Cross-edge to `_observability.md` (cost roll-up plumbing — shared with LLM + embeddings cost), `_multitenancy.md`.

**Outcome:** per-call cost estimator on each adapter (Qdrant Cloud pricing table, pgvector storage estimator, Weaviate Cloud pricing); per-KB and per-tenant cost counters; quota-enforcement hook before `upsert_records` that rejects when a tenant exceeds its vector budget; cost surfaces aggregated alongside LLM + embeddings cost in the shared cost-attribution module.

---

### Provisional cross-file edges

- Epic 4 (snapshot tooling) depends on object-store adapter contracts in `storage.md` and on a periodic job runner in `agent.md`; snapshot retention policy lives in `_infra.md`.
- Epic 5 (namespace reshape) is depended on by `embeddings.md` Epic 6 (model versioning + backfill) — model swap requires non-destructive reshape.
- Epic 6 (sharding/replication) depends on cluster topology decisions in `_infra.md` (Qdrant cluster mode, pgvector read-replicas).
- Epic 7 (rich filters) is depended on by `rag.md` (RAG predicates) and `monitoring.md` (alert evidence-pack queries).
- Epic 8 (hybrid search) is depended on by `rag.md` (context builder learns to set `query_text`).
- Epic 9 (delete-by-source-doc completeness) depends on the document-delete API route in `api.md` and is observed by `monitoring.md` (event consumers).
- Epic 10 (tenant scoping) depends on the tenant-resolution surface in `_multitenancy.md` and on auth contextvars in `_security.md`.
- Epic 11 (dimension governance) depends on `embeddings.md` Epic 1 (`get_model_info()` on embedder) — the preflight needs the embedder to advertise its dimension.
- Epic 12 (health probes) depends on the readiness-endpoint contract in `_observability.md` and on worker readiness wiring in `agent.md`.
- Epic 13 (observability) depends on the telemetry stack and metric naming in `_observability.md`; the recall@k harness depends on ground-truth artifact storage in `storage.md`.
- Epic 14 (cost tracking) depends on the shared cost-attribution surface in `_observability.md` (same plumbing as LLM + embeddings cost) and on tenant resolution in `_multitenancy.md`.

### Open questions

1. Epic 2 / Epic 3 — should pgvector and Weaviate ship together (one "extra adapters" epic) or sequenced (pgvector first because Postgres is already in the stack via `database/`)? Sequencing matters for the shared contract test suite's design.
2. Epic 4 (snapshot tooling) — does the in-memory adapter need snapshot support at all, or is a stub `NotImplementedError` acceptable since in-memory is dev/test only? Test fixtures may want JSON round-trip for replay debugging.
3. Epic 5 (namespace reshape) — blue/green vs in-place. Blue/green doubles peak storage during migration; in-place blocks writes. The right choice depends on whether the platform tolerates write downtime during reshape — needs an SLO decision.
4. Epic 6 (sharding) — what's the prod load target the benchmark should be sized for? Architecture §6 (cycle KBs) implies per-cycle KBs are bounded but the reference policy KB may be millions of vectors. Pick a representative working-set size.
5. Epic 7 (rich filters) — should the new filter model be exposed at the public API as a structured DSL or kept service-internal with the API translating from a flatter query shape? Influences API stability.
6. Epic 9 — should the event for source-doc delete be a new `VectorsDocumentDeletedEvent` or reuse `VectorsDeletedEvent` with an optional `source_document_id`? Schema evolution implications for monitoring consumers.
7. Epic 10 (tenant scoping) — defer to `_multitenancy.md` for the cross-cutting decision (collection-prefix vs per-cluster vs native multi-tenancy) and inherit it here, or make the decision here because Qdrant collection naming is module-local?
8. Epic 13 (recall@k) — is a ground-truth eval set within scope of this module (vectorstore owns the harness) or does it belong to `rag.md` (RAG owns retrieval quality, vectorstore only exposes hooks)?
