# vectorstore backlog

> **Scope:** Vector store protocol + adapters (in-memory, Qdrant; pgvector + Weaviate roadmap), snapshot/backup, sharding, hybrid search, dimension validation, tenant scoping.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story vectorstore.01: Expand live Qdrant integration coverage to every protocol method

**ID:** vectorstore.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** vectorstore maintainer,
**I need** every `VectorStoreProtocol` method exercised against a live Qdrant in CI,
**so that** payload encoding, deterministic point IDs, filter translation, and dimension-mismatch behavior cannot regress silently behind fake-client coverage.

### Current State
- Only two `@pytest.mark.integration` tests run against a live Qdrant — `test_qdrant_vector_store_round_trip_search` and `test_qdrant_vector_store_live_delete_namespace` (`backend/tests/vectorstore/test_qdrant_adapter.py:598`, `:650`).
- `get_record`, `count_records`, `delete_record`, `delete_by_source_document`, filter translation, dimension-mismatch rejection, and missing-collection behavior have only fake-client coverage in the same file.
- The float `gte`/`lte` range encoding (`backend/vectorstore/adapters/qdrant_adapter.py:443-446`) is unverified against a real Qdrant server.
- 1.0 spec § "Testing And Release Gates" required live coverage of *all* protocol methods (`docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md:167`).

### Acceptance Criteria
- [ ] New `@pytest.mark.integration` tests in `backend/tests/vectorstore/test_qdrant_adapter.py` cover `get_record`, `count_records`, `delete_record`, `delete_by_source_document`, filter translation (string + numeric + float-range), dimension-mismatch rejection, and missing-collection lookup.
- [ ] Each live test uses an ephemeral collection (`pytest-<uuid>-<test>`) and cleans up on teardown via a shared fixture.
- [ ] `QDRANT_URL` env var gates the suite; tests skip cleanly when unset.
- [ ] CI runs the integration suite against the docker-compose Qdrant service in a dedicated job.
- [ ] `backend/vectorstore/README.md` documents the live-test harness, the env var, and the local invocation command.

### Verification
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_adapter.py -v` green against the dev `docker compose -f docker-compose.dev.yaml up qdrant` instance.
- CI job for the integration suite is green on a representative PR.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/tests/vectorstore/test_qdrant_adapter.py` (modify)
- `backend/tests/vectorstore/conftest.py` (modify | new — shared ephemeral-collection fixture)
- `.github/workflows/` (modify — add or extend the integration-test job)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.02: Add pgvector adapter against the existing protocol

**ID:** vectorstore.02
**Status:** planned
**Prerequisites:** [database.01]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator running small or single-node deployments,
**I need** a pgvector-backed vector store that reuses the existing Postgres deployment,
**so that** lighter installations can avoid standing up a separate Qdrant cluster while keeping `VectorStoreProtocol` contract parity.

### Current State
- Architecture §3 (line 119) and §5.2 (line 137) list pgvector as a roadmap backend, but no implementation exists in `backend/vectorstore/adapters/`.
- `VectorStoreConfig.backend: Literal["qdrant", "in_memory"]` (`backend/config/schema.py:109`) currently rejects `"pgvector"`.
- `get_vectorstore_service` in `backend/api/dependencies.py` has no pgvector resolution branch.
- CLAUDE.md "Hard Rules" §2 forbids widening the literal until protocol + factory wiring + contract tests land.
- `database/` module ships a `ConnectionProvider` (`backend/database/connection.py`) that already manages a pooled Postgres connection, so a pgvector adapter does not need a second pool.

### Acceptance Criteria
- [ ] `backend/vectorstore/adapters/pgvector_adapter.py` implements every `VectorStoreProtocol` method against the `pgvector` extension.
- [ ] Adapter reuses `database.ConnectionProvider` and creates per-KB tables (or a single table with KB-partitioned indexes) lazily on first `upsert_records`.
- [ ] Optional dep added as `[pgvector]` extra in `backend/pyproject.toml`; gated import follows the pattern used by the Qdrant adapter.
- [ ] Shared adapter contract test suite in `backend/tests/vectorstore/test_adapter_contract.py` covers upsert, search w/ filters, get_record, count_records, delete_record, delete_namespace, delete_by_source_document, dimension mismatch, missing namespace — and is parametrized over `in_memory`, `qdrant` (integration), `pgvector` (integration).
- [ ] `VectorStoreConfig.backend` widened to `Literal["qdrant", "in_memory", "pgvector"]` only after the contract suite passes; factory wiring extended in `backend/api/dependencies.py` and `backend/agent/coordinator.py`.
- [ ] Live tests under `@pytest.mark.integration` gated on `POSTGRES_URL`; CI job runs them against the dev compose Postgres.
- [ ] `backend/vectorstore/README.md` and `docs/architecture.md` §5.2 updated to mark pgvector shipped.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green (unit + contract).
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_pgvector_adapter.py -v` green against dev Postgres with `pgvector` extension installed.
- `uv run --project backend pyright backend/vectorstore` clean.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/adapters/pgvector_adapter.py` (new)
- `backend/vectorstore/adapters/__init__.py` (modify)
- `backend/tests/vectorstore/test_adapter_contract.py` (new | modify)
- `backend/tests/vectorstore/test_pgvector_adapter.py` (new)
- `backend/config/schema.py` (modify — widen Literal, dependent validation)
- `backend/api/dependencies.py` (modify — factory branch)
- `backend/agent/coordinator.py` (modify — composition wiring)
- `backend/pyproject.toml` (modify — `[pgvector]` extra)
- `backend/vectorstore/README.md` (modify)
- `docs/architecture.md` (modify)

---

## Story vectorstore.03: Add Weaviate adapter against the existing protocol

**ID:** vectorstore.03
**Status:** planned
**Prerequisites:** [vectorstore.02]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator evaluating managed vector-database options,
**I need** a Weaviate-backed vector store implementation behind the same protocol,
**so that** deployments that prefer Weaviate Cloud or its class-per-tenant model can run chiliAI without forking the vectorstore module.

### Current State
- Architecture §3 (line 119) and §5.2 (line 137) list Weaviate as a roadmap adapter.
- No `WeaviateVectorStore` exists in `backend/vectorstore/adapters/`; `weaviate-client` is not listed in `backend/pyproject.toml`.
- `get_vectorstore_service` in `backend/api/dependencies.py` has no Weaviate branch.
- Weaviate's class-per-tenant model and native `hybrid()` query path is a distinct shape from Qdrant collections — the shared contract suite from vectorstore.02 needs to cover it.

### Acceptance Criteria
- [ ] `backend/vectorstore/adapters/weaviate_adapter.py` implements every `VectorStoreProtocol` method.
- [ ] Class/collection naming maps deterministically from `knowledge_base_id` (e.g., `Chili_<sanitized_kb_id>`) and survives `delete_namespace` + recreate.
- [ ] `weaviate-client` added as `[weaviate]` optional extra in `backend/pyproject.toml`; gated import.
- [ ] Adapter passes the shared contract suite introduced in vectorstore.02.
- [ ] `VectorStoreConfig.backend` widened to include `"weaviate"`; factory wiring extended.
- [ ] Live tests under `@pytest.mark.integration` gated on `WEAVIATE_URL`; CI runs them against a Weaviate service in compose.
- [ ] `backend/vectorstore/README.md` and `docs/architecture.md` §5.2 updated to mark Weaviate shipped.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_weaviate_adapter.py -v` green with `WEAVIATE_URL` set.
- `uv run --project backend pyright backend/vectorstore` clean.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/adapters/weaviate_adapter.py` (new)
- `backend/vectorstore/adapters/__init__.py` (modify)
- `backend/tests/vectorstore/test_weaviate_adapter.py` (new)
- `backend/config/schema.py` (modify — widen Literal)
- `backend/api/dependencies.py` (modify — factory branch)
- `backend/agent/coordinator.py` (modify — composition wiring)
- `backend/pyproject.toml` (modify — `[weaviate]` extra)
- `docker-compose.dev.yaml` (modify — add Weaviate service for integration tests)
- `backend/vectorstore/README.md` (modify)
- `docs/architecture.md` (modify)

---

## Story vectorstore.04: Add snapshot and backup tooling for vector namespaces

**ID:** vectorstore.04
**Status:** planned
**Prerequisites:** [storage.01, agent.01, _infra.01]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator,
**I need** scheduled snapshots of each KB's vector namespace pushed to object storage,
**so that** a corrupted or accidentally-deleted index can be restored without re-running hours of ingestion and embedding compute.

### Current State
- No snapshot or restore code path exists in `backend/vectorstore/` — `grep -ri "snapshot\|backup" backend/vectorstore/` returns nothing.
- The complete-backlog design spec §5 cites `vectorstore.04 Qdrant snapshot scheduling` as the canonical Ready-set example (`docs/superpowers/specs/2026-05-24-complete-backlog-design.md:210`).
- Qdrant ships native snapshot APIs (`POST /collections/{c}/snapshots`); pgvector backups go through `pg_dump`; the in-memory adapter has no persistence.
- Without snapshots, recovery from index corruption requires full re-ingest + re-embed, which can be hours of LLM/embedder compute per KB.

### Acceptance Criteria
- [ ] `VectorSnapshotProtocol` added as an optional extension surface on `backend/vectorstore/adapters/protocols.py` declaring `create_snapshot(kb_id) -> SnapshotDescriptor`, `restore_snapshot(kb_id, descriptor, mode: Literal["replace", "merge"])`, and `list_snapshots(kb_id) -> list[SnapshotDescriptor]`.
- [ ] Qdrant adapter implements the protocol by invoking the native snapshot API and uploading the resulting file to object storage via the `storage` module.
- [ ] In-memory adapter implements a JSON round-trip (records + metadata) sufficient for test replay.
- [ ] Per-adapter snapshot includes a SHA-256 checksum and stored dimension; restore verifies both before swapping.
- [ ] Periodic snapshot job registered in `backend/agent/coordinator.py` with cadence driven by `VectorStoreConfig.snapshot` (new sub-config: `enabled`, `cron`, `retention_count`).
- [ ] Snapshot artifacts land at `vectorstore/snapshots/{kb_id}/{utc_timestamp}-{request_id}.{ext}` in the configured object store; retention policy prunes oldest beyond `retention_count`.
- [ ] Unit + integration tests cover snapshot/restore round-trip on in-memory (always) and Qdrant (`@pytest.mark.integration`).
- [ ] `_infra.md`-owned CronJob manifest references the snapshot job (cross-edge handoff documented).

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including round-trip cases.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_snapshot.py -v` green against dev Qdrant + MinIO.
- `uv run --project backend pyright backend/vectorstore backend/agent/coordinator.py` clean.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/adapters/protocols.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/service.py` (modify — expose snapshot methods)
- `backend/vectorstore/service_models.py` (modify — `SnapshotDescriptor`)
- `backend/config/schema.py` (modify — `VectorStoreSnapshotConfig`)
- `backend/agent/coordinator.py` (modify — schedule job)
- `backend/tests/vectorstore/` (new test files)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.05: Add explicit namespace lifecycle with blue/green dimension reshape

**ID:** vectorstore.05
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator swapping embedder models,
**I need** explicit `create_namespace` and `reshape_namespace` operations on the vector store,
**so that** dimension changes migrate non-destructively without dropping the live index or losing audit history.

### Current State
- Namespace creation is implicit (lazy on first `upsert_records` — `backend/vectorstore/adapters/qdrant_adapter.py:142-147`, `backend/vectorstore/adapters/in_memory.py:42-43`).
- No `create_namespace(kb_id, dimension)` exists to provision a collection ahead of writes (so a readiness probe can confirm the collection is ready).
- No `reshape_namespace(kb_id, new_dimension)` exists; dimension changes raise `VectorDimensionMismatchError` (`backend/vectorstore/adapters/qdrant_adapter.py:317-322`, `backend/vectorstore/adapters/in_memory.py:36-40`).
- Today's only recovery from a dimension change is `delete_knowledge_base` + full re-index, which is destructive and silently discards the index audit log.
- 1.0 spec deferred this; once embeddings model versioning lands (cross-edge `embeddings.06`), reshape becomes a hard requirement.

### Acceptance Criteria
- [ ] `VectorStoreProtocol` adds `create_namespace(knowledge_base_id, dimension)` and `describe_namespace(knowledge_base_id) -> NamespaceInfo` (fields: `dimension`, `record_count`, `created_at`, `backend`).
- [ ] `VectorServiceProtocol` adds the same methods (pass-through).
- [ ] `VectorStoreProtocol` adds `reshape_namespace(knowledge_base_id, new_dimension, strategy: Literal["blue_green"]) -> ReshapeReceipt` that creates a new collection, copies records via a caller-provided re-embed callback, atomically swaps the alias, and deletes the old collection on success.
- [ ] Both `in_memory` and `qdrant` adapters implement all three methods; Qdrant uses collection aliases for atomic swap.
- [ ] Double-`create_namespace` of an already-existing namespace with matching dimension is idempotent; mismatched dimension raises a typed exception with both dimensions reported.
- [ ] Reshape rollback test: a forced failure during copy leaves the old collection serving reads unchanged.
- [ ] `backend/vectorstore/README.md` documents the lifecycle contract and the blue/green reshape flow.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including create/describe/reshape and rollback cases.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_lifecycle.py -v` green against dev Qdrant.
- `uv run --project backend pyright backend/vectorstore` clean.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/adapters/protocols.py` (modify)
- `backend/vectorstore/protocols.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/service_models.py` (modify — `NamespaceInfo`, `ReshapeReceipt`)
- `backend/vectorstore/exceptions.py` (modify)
- `backend/tests/vectorstore/` (modify | new)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.06: Add sharding and replication knobs for production Qdrant load

**ID:** vectorstore.06
**Status:** planned
**Prerequisites:** [_infra.01]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator running production claim-stream volumes,
**I need** Qdrant collections created with explicit shard, replica, and HNSW tuning derived from config,
**so that** single-shard defaults do not throttle million-vector KBs and high-availability is achievable through replication.

### Current State
- `QdrantVectorStore._ensure_collection` creates collections with `VectorParams(size=dimension, distance=self._distance)` only (`backend/vectorstore/adapters/qdrant_adapter.py:325-331`) — no `shard_number`, `replication_factor`, `write_consistency_factor`, `on_disk_payload`, or `hnsw_config`.
- `VectorStoreConfig` (`backend/config/schema.py:106-113`) exposes `backend`, `uri`, `dimensions`, `distance_metric` only.
- For prod claims-stream volumes (millions of vectors per KB), the single-shard default ceilings throughput and storage; lack of replication is a single-point-of-failure.
- Cross-edge to `_infra.md` (Qdrant cluster topology decisions).

### Acceptance Criteria
- [ ] `VectorStoreConfig` gains nested `QdrantTuningConfig` (`shard_number`, `replication_factor`, `write_consistency_factor`, `on_disk_payload`, `hnsw_m`, `hnsw_ef_construct`) with safe defaults documented inline.
- [ ] Optional per-KB override surface: `VectorStoreConfig.kb_overrides: dict[str, QdrantTuningConfig]` so large KBs can be tuned independently.
- [ ] `QdrantVectorStore._ensure_collection` passes all knobs through to Qdrant on creation; existing collections are not mutated (knobs are creation-time settings — change-detection logs a warning).
- [ ] pgvector and Weaviate adapters record their equivalent knobs (or document the absence) in a parallel config block so the surface is uniform across backends.
- [ ] Documented load-test budget (`docs/vectorstore/load_budget.md` or `backend/vectorstore/README.md` § Load Targets): ≥ 10k vectors/sec sustained upsert, p95 search < 100 ms at 1 M vectors per KB.
- [ ] Smoke benchmark in `backend/tests/vectorstore/bench_qdrant.py` (gated behind a `@pytest.mark.benchmark` marker) records p50/p95 search latency against a synthetic 100 k-vector KB and writes results to `bench-results/`.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green.
- `uv run --project backend pytest -m benchmark backend/tests/vectorstore/bench_qdrant.py` reports numbers within the documented budget on the reference dev machine.
- `uv run --project backend pyright backend/vectorstore` clean.
- Manual: inspect a freshly-created collection with `curl $QDRANT_URL/collections/<kb>` and verify the configured shard/replica counts.

### Code touch points
- `backend/config/schema.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/pgvector_adapter.py` (modify if shipped)
- `backend/vectorstore/adapters/weaviate_adapter.py` (modify if shipped)
- `backend/tests/vectorstore/bench_qdrant.py` (new)
- `backend/vectorstore/README.md` (modify)
- `docs/architecture.md` (modify — note new tuning surface)

---

## Story vectorstore.07: Add range, list, and compound metadata filters

**ID:** vectorstore.07
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** RAG or monitoring service author,
**I need** the vector-search API to accept range, list, and compound (must/should/must_not) metadata filters,
**so that** queries like "claims with `amount > 5000` in `state in [TN, KY]`" execute server-side instead of forcing over-fetch + Python post-filter.

### Current State
- Service-level and adapter-level filters accept `dict[str, MetadataValue]` (scalar equality only — `backend/vectorstore/models.py:11`, `backend/vectorstore/service_models.py:95`).
- 1.0 spec § "Metadata And Filtering" explicitly defers list filters, range filters, and faceting.
- Qdrant supports `Range`, `MatchAny`, `should`, `must_not` natively; the float-equality hack at `backend/vectorstore/adapters/qdrant_adapter.py:443-446` already encodes a range filter for floats.
- Without these, monitoring/RAG over-fetch and filter in Python, which inflates latency and cost.

### Acceptance Criteria
- [ ] New `MetadataFilter` model in `backend/vectorstore/models.py` supports `eq`, `range(gte, lte)`, `in_list`, plus compound `must`, `should`, `must_not` clauses.
- [ ] Back-compat shim: existing callers passing `dict[str, MetadataValue]` continue to work; the service converts to a `must`-only `MetadataFilter`.
- [ ] Per-adapter translation: Qdrant (native filter DSL), pgvector (`WHERE` clause builder), Weaviate (`where` builder), in-memory (Python predicate).
- [ ] `VectorSearchRequest.filters` typed as `MetadataFilter | dict[str, MetadataValue] | None`.
- [ ] Shared adapter contract suite (vectorstore.02) extended with cases covering each combinator and each operator, including nested compound shapes.
- [ ] `backend/vectorstore/README.md` documents the filter DSL with examples for each backend.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including new filter cases.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_adapter.py -v` green covering filter translation against live Qdrant.
- `uv run --project backend pyright backend/vectorstore` clean.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/models.py` (modify)
- `backend/vectorstore/service_models.py` (modify)
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/adapters/pgvector_adapter.py` (modify if shipped)
- `backend/vectorstore/adapters/weaviate_adapter.py` (modify if shipped)
- `backend/tests/vectorstore/` (modify)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.08: Add hybrid search (vector + keyword) on adapters that support it

**ID:** vectorstore.08
**Status:** planned
**Prerequisites:** [vectorstore.07, graph.08]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** RAG context builder,
**I need** vector search optionally fused with keyword/BM25 scoring on a single request,
**so that** exact-match terms (NPI numbers, ICD codes) are not buried by dense-vector similarity noise.

### Current State
- Only dense vector search is exposed — `VectorSearchRequest` carries `query_vector` but no `query_text` (`backend/vectorstore/service_models.py:89-101`).
- Qdrant supports BM25 / sparse vectors via the `Query` payload; Weaviate exposes `hybrid()` natively; pgvector pairs with `tsvector`.
- 1.0 spec defers hybrid; architecture §7 (RAG pipeline) calls for keyword + vector retrieval for exact-match cases.
- `rag` retrieval is pure dense cosine via `ServiceContextRetriever` (`backend/api/_rag_bridges.py:104-142`) — there is no keyword path.

### Acceptance Criteria
- [ ] `VectorSearchRequest` extended with `query_text: str | None` and `hybrid: HybridConfig | None` (`alpha`, `keyword_field`); when `hybrid` is set, `query_text` is required.
- [ ] `VectorStoreProtocol` gains a `supports_hybrid: bool` class-level capability flag; service-level `search` raises a typed error when hybrid is requested against a non-supporting adapter.
- [ ] Qdrant adapter implements hybrid via sparse vectors or BM25 payload index; Weaviate adapter uses `hybrid()`; pgvector adapter uses `tsvector` + `ts_rank_cd` joined to vector similarity; in-memory adapter simulates with substring-bonus boost (deterministic, test-friendly).
- [ ] Hybrid rank-fusion uses RRF or alpha-weighted score (documented choice) with adapter-level implementation tested for stable ordering.
- [ ] Contract suite covers dense-only, keyword-only (alpha=0), and hybrid (0 < alpha < 1) retrieval shapes; rank shifts vs dense-only are asserted on a synthetic dataset.
- [ ] `backend/vectorstore/README.md` documents the hybrid API and adapter capability matrix.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including hybrid cases.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_hybrid.py -v` green against dev Qdrant.
- `uv run --project backend pyright backend/vectorstore` clean.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/service_models.py` (modify)
- `backend/vectorstore/adapters/protocols.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/adapters/pgvector_adapter.py` (modify if shipped)
- `backend/vectorstore/adapters/weaviate_adapter.py` (modify if shipped)
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/exceptions.py` (modify)
- `backend/tests/vectorstore/` (new | modify)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.09: Wire `delete_by_source_document` into the document-delete API and harden edge cases

**ID:** vectorstore.09
**Status:** planned
**Prerequisites:** [api.01, events.01]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As an** analyst deleting an ingested document,
**I need** the document-delete API to cascade vector cleanup and emit an observable event,
**so that** stale embeddings never leak into RAG results and downstream consumers see the deletion.

### Current State
- `delete_by_source_document` ships on the protocol, in-memory adapter, Qdrant adapter, and service (`backend/vectorstore/service.py:216-232`, `backend/vectorstore/adapters/protocols.py:40-44`, `backend/vectorstore/adapters/in_memory.py:111-127`, `backend/vectorstore/adapters/qdrant_adapter.py:261-299`).
- Architecture §7 (line 780) calls out: "Graph/vector cascade cleanup via `delete_by_source_document` is called on the re-upload (changed-content) path; it is not yet wired to the document-delete endpoint."
- No `DELETE /knowledgebases/{kb_id}/documents/{document_id}` route invokes the cascade.
- No event is published on this delete (unlike `delete_knowledge_base` which emits `VectorsDeletedEvent` — `backend/vectorstore/service.py:208-213`).
- Edge cases unverified: missing `SOURCE_DOCUMENT_ID_KEY` in metadata, records spanning multiple source documents, very large deletes (>10 k vectors via Qdrant scroll vs single delete-by-filter), and concurrency with in-flight indexing of the same doc.

### Acceptance Criteria
- [ ] `DELETE /knowledgebases/{kb_id}/documents/{document_id}` route in `backend/api/routers/` invokes `VectorService.delete_by_source_document` and propagates the response.
- [ ] `VectorService.delete_by_source_document` publishes either a new `VectorsDocumentDeletedEvent` or reuses `VectorsDeletedEvent` with a `source_document_id` field set (decision recorded in `backend/events/types.py` and `backend/vectorstore/README.md`).
- [ ] Missing `SOURCE_DOCUMENT_ID_KEY` on stored records is handled deterministically (documented: no-op with zero count vs raising) and tested.
- [ ] Records associated with multiple source documents are only removed when *every* `source_document_id` they reference has been deleted; partial-deletion logic is tested.
- [ ] Large-delete path (>10 k vectors) uses Qdrant's `delete_by_filter` (no scroll) and is exercised by an integration test.
- [ ] Concurrency test interleaves `upsert_records` and `delete_by_source_document` for the same `source_document_id` and asserts eventual-consistency invariants are documented and met.
- [ ] Cross-edge: `monitoring.md` consumer for the new/reused event is referenced and stubbed.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore backend/tests/api -v` green including new edge-case tests.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_adapter.py -v` green for the large-delete path.
- Manual smoke: upload a document, `DELETE` it via the API, confirm `VectorService.count` for its KB drops by the expected amount, confirm the event is visible on the Redis stream.

### Code touch points
- `backend/api/routers/knowledgebases.py` (modify) or `backend/api/routers/documents.py` (modify | new)
- `backend/vectorstore/service.py` (modify)
- `backend/events/types.py` (modify — new event or extend `VectorsDeletedEvent`)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify — large-delete path)
- `backend/tests/vectorstore/` (modify)
- `backend/tests/api/` (modify)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.10: Add tenant-scoped collections / namespaces

**ID:** vectorstore.10
**Status:** planned
**Prerequisites:** [_multitenancy.08, _security.01]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator running multi-tenant deployments,
**I need** vector namespaces scoped per tenant with default-deny cross-tenant access,
**so that** two tenants sharing the same `knowledge_base_id` cannot read or overwrite each other's vectors.

### Current State
- Collection naming is `chili_{knowledge_base_id}` (`backend/vectorstore/adapters/qdrant_adapter.py:415`) with no tenant prefix.
- `VectorStoreProtocol` operations take only `knowledge_base_id`; there is no `tenant_id` parameter, no default-deny filter, and no per-tenant collection-list isolation.
- Architecture §14.2 lists multi-tenancy isolation as Medium priority; §7 (line 1291) calls for "separate vector store namespaces" per tenant.
- Today, two tenants writing to the same `knowledge_base_id` value collide silently in the same Qdrant collection.

### Acceptance Criteria
- [ ] Tenant-scoping strategy decided and documented in `backend/vectorstore/README.md` (choice between (a) `tenant_id` prefix in collection name, (b) per-tenant Qdrant cluster, (c) Qdrant native multi-tenancy via payload isolation).
- [ ] `VectorStoreProtocol` operations accept `tenant_id` either as an explicit parameter or via a `tenant_id` ContextVar resolved by auth middleware (decision recorded).
- [ ] `VectorServiceProtocol` and `service.py` pass the tenant down to every adapter call.
- [ ] Cross-tenant query attempts default-deny: passing tenant A's id while operating on tenant B's KB raises a typed error.
- [ ] All adapters (in-memory, Qdrant, pgvector if shipped, Weaviate if shipped) implement the chosen strategy uniformly.
- [ ] Tests cover tenant isolation across `upsert_records`, `search`, `get_record`, `count_records`, `delete_record`, `delete_namespace`, `delete_by_source_document` — including the explicit cross-tenant default-deny case.
- [ ] Migration plan documented for existing un-tenanted collections (one-shot script or backward-compatible read fallback).

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including tenant-isolation cases.
- `uv run --project backend pytest -m integration backend/tests/vectorstore/test_qdrant_tenant.py -v` green against dev Qdrant.
- Manual: create two tenants, index identical KB ids, confirm collection names diverge in Qdrant and that cross-tenant reads return zero results.

### Code touch points
- `backend/vectorstore/adapters/protocols.py` (modify)
- `backend/vectorstore/protocols.py` (modify)
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/adapters/pgvector_adapter.py` (modify if shipped)
- `backend/vectorstore/adapters/weaviate_adapter.py` (modify if shipped)
- `backend/vectorstore/exceptions.py` (modify)
- `backend/tests/vectorstore/` (modify | new)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.11: Cross-validate embedder dimension against vector collection at boot and on swap

**ID:** vectorstore.11
**Status:** planned
**Prerequisites:** [embeddings.01]
**Unblocks:** []
**Estimated size:** S
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator,
**I need** boot-time validation that the configured embedder, vector-store config, and existing collection all agree on dimension,
**so that** mis-configured embedders fail fast at startup instead of silently producing dimension-mismatch errors on the first search.

### Current State
- `VectorStoreConfig.dimensions` is declared in config (`backend/config/schema.py:111`) but cross-validation with `EmbeddingsConfig.dimensions` is explicitly deferred — the schema comment at `backend/config/schema.py:113` reads "Cross-validation with EmbeddingsConfig.dimensions is deferred to E1-S06."
- `QdrantVectorStore._validate_query_dimension` (`backend/vectorstore/adapters/qdrant_adapter.py:310-314`) compares the *query* vector against `self._config.dimensions`, not against the embedder's actual output dimension.
- An embedder/config mismatch only surfaces on the first search; an embedder/collection mismatch only surfaces on the first upsert.
- No preflight asks the embedder for its declared dimension and asserts equality with the collection's stored dimension.

### Acceptance Criteria
- [ ] Boot-time preflight in `create_vector_service` (or a `FastAPI` startup hook in `backend/api/app.py`) asks the bound embedder via `get_model_info()` (introduced by `embeddings.01`) for its dimension.
- [ ] Preflight asserts `embedder.dimensions == VectorStoreConfig.dimensions`; mismatch raises `ConfigurationError` with both values reported.
- [ ] When a collection already exists, preflight also calls `describe_namespace` (from `vectorstore.05`) and asserts the stored dimension matches; mismatch logs the recommended reshape command and raises.
- [ ] Config loader (`backend/config/schema.py`) gains a cross-field validator that warns (not errors) when `EmbeddingsConfig.dimensions != VectorStoreConfig.dimensions`.
- [ ] Tests cover the three preflight outcomes: all match (pass), embedder/config mismatch (raise), collection/config mismatch (raise with reshape hint).
- [ ] `backend/vectorstore/README.md` documents the embedder swap workflow that points to `vectorstore.05` reshape.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore backend/tests/config -v` green.
- `uv run --project backend pyright backend/vectorstore backend/config` clean.
- Manual: set `embeddings.dimensions=384` and `vectorstore.dimensions=768` in a test config, start the API, confirm a clear `ConfigurationError` at boot.

### Code touch points
- `backend/api/dependencies.py` (modify — preflight in `get_vectorstore_service`)
- `backend/api/app.py` (modify — startup hook)
- `backend/config/schema.py` (modify — cross-field warning)
- `backend/vectorstore/service.py` (modify — preflight entry point)
- `backend/tests/vectorstore/` (modify)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.12: Add vector-store health probes for worker and API readiness

**ID:** vectorstore.12
**Status:** planned
**Prerequisites:** [_observability.01]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator,
**I need** the vector-store adapter to expose a `health_check` consumed by the API readiness endpoint and the worker startup,
**so that** an unreachable or mis-configured Qdrant is visible to liveness/readiness probes instead of failing on the first user query.

### Current State
- No `ping()` or `health_check()` exists on `VectorStoreProtocol` or `VectorServiceProtocol` (`backend/vectorstore/protocols.py:18-43`, `backend/vectorstore/adapters/protocols.py:11-44`).
- No readiness endpoint in `backend/api/routers/` references vectorstore.
- The Qdrant adapter constructs `QdrantClient` at init (`backend/vectorstore/adapters/qdrant_adapter.py:127-128`) but never pings; misconfigured `uri` only surfaces on first upsert/search.
- The agent worker (`backend/agent/coordinator.py:1706`) has no startup probe for the vector store.

### Acceptance Criteria
- [ ] `VectorStoreProtocol` and `VectorServiceProtocol` declare `health_check() -> VectorStoreHealth` (fields: `status: Literal["ok", "degraded", "down"]`, `latency_ms`, `backend`, `collections_present`, `error: str | None`).
- [ ] In-memory adapter always returns `ok` with `0` latency.
- [ ] Qdrant adapter probes `cluster_status` (or `collections.get_collections`) and reports the result.
- [ ] pgvector adapter probes via `SELECT 1` on the connection pool; Weaviate adapter probes `meta()` (where applicable).
- [ ] API readiness endpoint (`/ready` or equivalent in `_observability.01`) includes vectorstore status and returns 503 when `status == "down"`.
- [ ] Agent worker `backend/agent/coordinator.py` waits up to a configured `startup_probe_timeout_s` for the probe to pass before consuming events; on timeout, logs a structured error and exits with non-zero status.
- [ ] Tests cover the probe with both reachable and unreachable backends for in-memory and Qdrant (the latter via a fake client that raises).

### Verification
- `uv run --project backend pytest backend/tests/vectorstore backend/tests/api -v` green.
- `uv run --project backend pyright backend/vectorstore backend/api` clean.
- Manual: stop the Qdrant container, hit `/ready`, confirm 503 with vectorstore status `down`; start Qdrant, confirm 200.

### Code touch points
- `backend/vectorstore/adapters/protocols.py` (modify)
- `backend/vectorstore/protocols.py` (modify)
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/service_models.py` (modify — `VectorStoreHealth`)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/api/routers/health.py` (modify | new)
- `backend/agent/coordinator.py` (modify)
- `backend/tests/vectorstore/` (modify | new)

---

## Story vectorstore.13: Add vectorstore observability — metrics, traces, structured audit logs, recall@k harness

**ID:** vectorstore.13
**Status:** planned
**Prerequisites:** [_observability.05, storage.01]
**Unblocks:** []
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As an** SRE,
**I need** the vector-store adapters to emit Prometheus metrics, OTel spans, and structured audit logs, plus a recall@k regression harness,
**so that** I can answer "what is our p95 search latency on the claims KB?" and detect retrieval-quality regressions before users do.

### Current State
- `VectorService` and adapters emit no metrics, traces, or structured logs beyond a single warning when audit persistence fails (`backend/vectorstore/service.py:261-264`).
- No counters for `index_call_count`, `search_call_count`, `vectors_indexed_total`, or `vectors_deleted_total`; no histogram for `vector_search_duration_ms`.
- No OTel spans wrap adapter calls.
- Architecture §11.2 lists `graph_query_duration_seconds` as a required metric; an equivalent for vectorstore is missing.
- Recall@k regression tracking is impossible without a ground-truth eval harness.

### Acceptance Criteria
- [ ] Module metrics exported with `chili_vectorstore_` prefix: `chili_vectorstore_op_count{op, backend, status}`, `chili_vectorstore_op_duration_seconds{op, backend}` (histogram), `chili_vectorstore_batch_size{op}` (histogram), `chili_vectorstore_vectors_indexed_total{kb_id}`, `chili_vectorstore_vectors_deleted_total{kb_id, reason}`.
- [ ] OpenTelemetry spans wrap `upsert_records`, `search`, and namespace lifecycle operations with `kb_id`, `backend`, `record_count`, and `latency_ms` attributes.
- [ ] Structured audit log on writes/deletes (KB id, request id, counts) — no embedding payloads are logged.
- [ ] Recall@k evaluation harness in `backend/vectorstore/evaluation/` runs against a held-out ground-truth set per KB and emits `chili_vectorstore_recall_at_k{k, kb_id}`; ground-truth artifacts persisted via the `storage` module at `vectorstore/evaluation/{kb_id}/ground_truth.json`.
- [ ] Harness scheduled from `backend/agent/coordinator.py` on a configurable cadence (`VectorStoreConfig.evaluation.cron`); manual one-shot CLI also available.
- [ ] Dashboard panels declared in `_observability.md` (cross-edge handoff documented).
- [ ] Tests cover metric emission, span creation, audit-log shape, and a recall@k harness round-trip on a synthetic ground-truth set.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including telemetry cases.
- `uv run --project backend pyright backend/vectorstore` clean.
- Manual: run `docker compose -f docker-compose.dev.yaml up`, perform a few searches, scrape `/metrics`, confirm `chili_vectorstore_*` series populate; check OTel traces in the dev tracing UI.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/adapters/pgvector_adapter.py` (modify if shipped)
- `backend/vectorstore/adapters/weaviate_adapter.py` (modify if shipped)
- `backend/vectorstore/evaluation/` (new — harness module)
- `backend/agent/coordinator.py` (modify — schedule harness)
- `backend/config/schema.py` (modify — `VectorStoreEvaluationConfig`)
- `backend/tests/vectorstore/` (modify | new)
- `backend/vectorstore/README.md` (modify)

---

## Story vectorstore.14: Add per-provider cost tracking and quota enforcement

**ID:** vectorstore.14
**Status:** planned
**Prerequisites:** [_observability.05, _multitenancy.08]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-vectorstore-1-0-design.md

**As a** platform operator running a multi-tenant deployment,
**I need** per-call cost estimates and per-tenant quota enforcement on vector operations,
**so that** vector storage and search spend are attributable and a runaway tenant cannot exhaust the cluster.

### Current State
- No cost surface in `backend/vectorstore/` — vector storage cost (per-GB Qdrant Cloud, per-row pgvector, Weaviate Cloud per-object), search-API call cost, and snapshot/egress cost are all invisible.
- Architecture §14.2 calls out tenant-level resource attribution as a Medium-priority capability.
- Without it, multi-tenant cost allocation and quota enforcement (e.g., "tenant X exceeded 1 M vectors") are impossible.

### Acceptance Criteria
- [ ] `VectorCostEstimatorProtocol` added with `estimate_upsert_cost(record_count, dimension)`, `estimate_search_cost(record_count)`, and `estimate_storage_cost(record_count, dimension)`; pluggable per-backend (Qdrant Cloud pricing table, pgvector storage estimator, Weaviate Cloud pricing).
- [ ] `VectorService` invokes the estimator on every `index`, `search`, and `delete_*` call and emits `chili_vectorstore_cost_usd_total{tenant_id, kb_id, op, backend}` counter (cross-edge to `_observability.05`).
- [ ] `VectorStoreConfig` gains `quotas` sub-config: `max_vectors_per_tenant`, `max_cost_usd_per_tenant_per_day` (both optional; off by default).
- [ ] Quota-enforcement hook before `upsert_records` rejects with a typed `VectorQuotaExceededError` when the tenant exceeds its configured budget; the rejection includes the projected post-write count and the configured ceiling.
- [ ] Per-KB and per-tenant cost counters are scraped alongside LLM and embeddings cost in the shared cost-attribution dashboard (declared in `_observability.md`).
- [ ] Tests cover cost-estimator math for each adapter, quota acceptance below the ceiling, quota rejection above the ceiling, and counter emission.

### Verification
- `uv run --project backend pytest backend/tests/vectorstore -v` green including cost and quota cases.
- `uv run --project backend pyright backend/vectorstore` clean.
- Manual: configure a small `max_vectors_per_tenant`, attempt a bulk upsert, confirm rejection with the expected error payload; scrape `/metrics` and confirm cost counters populate.
- Coverage gate: ≥ 85% on `vectorstore` package.

### Code touch points
- `backend/vectorstore/adapters/protocols.py` (modify — `VectorCostEstimatorProtocol`)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `backend/vectorstore/adapters/pgvector_adapter.py` (modify if shipped)
- `backend/vectorstore/adapters/weaviate_adapter.py` (modify if shipped)
- `backend/vectorstore/service.py` (modify)
- `backend/vectorstore/exceptions.py` (modify — `VectorQuotaExceededError`)
- `backend/config/schema.py` (modify — `VectorStoreQuotasConfig`)
- `backend/tests/vectorstore/` (modify | new)
- `backend/vectorstore/README.md` (modify)
