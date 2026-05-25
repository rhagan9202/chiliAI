## File: docs/backlog/graph.md

**Scope:** Graph DB protocol + adapters (in-memory, Neo4j; Memgraph/Neptune roadmap), dual-graph contract, schema/index lifecycle, subgraph queries.

Source-of-truth audit of `backend/graph/` against `docs/architecture.md` §5.2 (graph row), §6 (KB / graph flows), §7.4 (dual-graph reads), §14.2 (future capabilities) and the live specs `2026-05-21-dual-graph-contract-design.md` and `2026-05-21-neo4j-graph-indexes-design.md`. Historical backlog `docs/graph_backlog_05_17.md` informed scope; done items skipped, intent carried forward where still unmet.

Done and intentionally **not** carried forward as epics:
- Neo4j composite constraint/index bootstrap (`_ensure_schema` at `backend/graph/adapters/neo4j_adapter.py:139`).
- Neo4j fulltext index for entity property search (commit b0fcc38; `entity_properties_fulltext` at `neo4j_adapter.py:153`).
- Dual-graph read protocol contract — `knowledge_base_ids: list[str]` on `get_entity`/`search_entities` already landed (`graph/protocols.py:21,37`, `graph/adapters/protocols.py:38,63`, resolver call sites in `api/routers/investigation.py:57,81,113`).
- `delete_by_source_document` shipped on both adapters (`graph/adapters/in_memory.py:216`, `neo4j_adapter.py:483`).
- Full 207 KB-delete cascade through `GraphService.delete_knowledge_base()`.

---

## Epic 1: Enforce relationship referential integrity in production mode

**Gap:** `InMemoryGraphRepository.upsert_relationships` (`backend/graph/adapters/in_memory.py:41`) and the Neo4j `MERGE (source)…MERGE (target)` pattern (`backend/graph/adapters/neo4j_adapter.py:228-229`) both silently create endpoint nodes when source/target IDs are missing. The in-memory TODO at `in_memory.py:21` explicitly flags this. No `GraphIntegrityError` exists in `graph/exceptions.py`.

**Outcome:** strict-mode default rejects dangling edges; legacy create-placeholder behavior is opt-in for import flows. Surfaced through `GraphService.upsert_task` and `upsert_records_graph` as a typed error.

---

## Epic 2: Add merge/version semantics and optimistic conflict detection on upserts

**Gap:** Entity upsert blindly overwrites properties (`in_memory.py:35-39`; Neo4j `SET entity.properties_json = row.properties_json` at `neo4j_adapter.py:184`). Only `update_entity_properties` merges (`service.py:173`). No `expected_version` check though `Entity.version` is stored — stale writes silently win.

**Outcome:** `GraphUpsertOptions` with `merge_properties | replace_properties | expected_version`. Replay of identical payload does not bump version. Stale-version writes raise a typed conflict.

---

## Epic 3: Add change detection and idempotent upsert receipts

**Gap:** `GraphService.upsert_task` (`backend/graph/service.py:49`) always writes the graph-update artifact and publishes `GraphUpdatedEvent` regardless of whether the graph changed. `GraphUpsertResult` (`graph/models.py:21`) reports `upserted_*_ids` only — no created/updated/unchanged/deleted partition. Downstream embeddings/analytics get spurious work on replay.

**Outcome:** content fingerprints stored per object; receipts distinguish created/updated/unchanged/deleted; `GraphUpdatedEvent` publish is gated on actual change in production mode (audit mode keeps always-publish).

---

## Epic 4: Make graph build tasks transactionally atomic at task scope

**Gap:** `GraphService` opens a fresh `repository.transaction(kb_id)` per entity batch and per relationship batch (`service.py:127, 151`). A failure in the 3rd batch leaves the first two committed. `BatchUpsertError` (`graph/exceptions.py`) reports counts but the task is not rolled back.

**Outcome:** task-scoped transaction wrapping all batches when adapter supports it; explicit partial-success mode otherwise; in-memory adapter rollback proven to restore entities, relationships, and adjacency indexes.

---

## Epic 5: Add filtered subgraph extraction for evidence packs

**Gap:** `GraphServiceProtocol.TODO(production)` at `backend/graph/protocols.py:16` calls out `get_subgraph(kb_id, entity_ids) -> SubgraphResult`. Adapters expose only `get_neighbors` (single root) and `get_entities` (full KB). Evidence-pack assembly currently has no efficient cross-edge fetcher — cross-edges to `monitoring.md` (alert evidence packs) and `analytics.md` (explainability subgraphs). Subgraph performance on large claims KBs is unverified.

**Outcome:** `get_subgraph(kb_ids, entity_ids, include_internal_relationships, expansion_depth)` on both adapters; Neo4j query uses the existing composite index; benchmark gate on subgraph fetch latency for evidence-pack-sized requests (e.g., ≤200 entities returns in <500ms p95 on Neo4j).

---

## Epic 6: Add relationship detail reads, pagination, and cursor stability

**Gap:** `graph/adapters/protocols.py:16` TODO calls out `get_relationship()` and pagination on `get_entities`/`get_relationships`. Today they return full unbounded lists (`in_memory.py:52`, `neo4j_adapter.py:256`). `get_entities_by_type` has SKIP/LIMIT but no cursor or filters. API `routers/graph.py` exposes only entity detail (24 lines). UI/RAG cannot page large KBs.

**Outcome:** repository methods `get_relationship`, `list_entities(filters, cursor)`, `list_relationships(filters, cursor)` with deterministic ordering; service models for paged reads; API surface follows in Epic 12.

---

## Epic 7: Improve entity search relevance and observability

**Gap:** In-memory search does a Python substring scan over string property values (`in_memory.py:159`). Neo4j search now uses the fulltext index (`neo4j_adapter.py:411`) but returns plain `list[Entity]` — no score, matched-field, total, or type filter exposed at the service layer. `search_entities` in `service.py:260` discards Lucene score.

**Outcome:** `EntitySearchHit` model carrying score, matched fields, snippet; service-level type/property filters; total or `next_cursor`; in-memory parity for tests with deterministic rank ordering.

---

## Epic 8: Bulk write throughput — batched UNWIND tuning and adapter benchmarks

**Gap:** `GraphService.batch_size = 500` is the only knob (`service.py:39`). Each batch round-trips serialized `properties_json` strings — `_dump_json_property` calls `json.dumps` per entity (`neo4j_adapter.py:673`). No throughput floor is asserted. Records pipeline (NPPES, DE-SynPUF) and claims streams write large volumes; no benchmark exists for entities/sec or relationships/sec on Neo4j with the new indexes.

**Outcome:** adapter benchmark target (e.g., ≥5k entities/sec, ≥3k relationships/sec on Neo4j in CI's docker compose); configurable `batch_size` per workload; UNWIND batch sizing tuned and documented; periodic flush + commit interval for very large loads.

---

## Epic 9: Add graph schema migrations and version metadata

**Gap:** `_ensure_schema` (`neo4j_adapter.py:139`) only issues `CREATE … IF NOT EXISTS`. No way to drop or alter an index/constraint, no schema-version table, no failure-mode for partial schema drift (e.g., constraint exists with a different shape). The spec at `2026-05-21-neo4j-graph-indexes-design.md` §2 explicitly defers a migration framework. Once analytics/dual-graph evolves (e.g., NPI property indexes per §7.4) the schema must change in lockstep with code.

**Outcome:** versioned schema migrations (forward-only, idempotent) recorded in a `:_SchemaVersion` node; `_ensure_schema` invokes pending migrations on boot; `drift_check()` lists declared-vs-observed indexes/constraints.

---

## Epic 10: Add constraint/index lifecycle drift detection and idempotent apply

**Gap:** `_ensure_schema` logs and continues on per-statement failure (`neo4j_adapter.py:161`). No telemetry on whether the constraint/index actually exists post-apply. Operators can't detect a partial bootstrap (e.g. DDL permission revoked mid-run, index removed manually). The deferred-tools warning in the spec is now real risk on long-lived prod databases.

**Outcome:** `verify_schema()` method enumerates `SHOW CONSTRAINTS` / `SHOW INDEXES` and asserts the declared set is present; `--strict` startup mode fails fast on drift; production deploy probe surfaces missing-index as 503.

---

## Epic 11: Add Memgraph and Neptune adapters with shared contract suite

**Gap:** Architecture §3 container catalog (line 118-119) and §5.2 module table list Memgraph and Neptune as roadmap backends, but `GraphDbConfig.backend: Literal["neo4j", "in_memory"]` (`backend/config/schema.py:100`) rejects either, and `api/dependencies.py:466 get_graph_repository` only resolves the two known backends. CLAUDE.md "Hard Rules" §2 explicitly forbids adding adapters to the literal without protocol + factory wiring + tests.

**Outcome:** declare `MemgraphGraphRepository` and `NeptuneGraphRepository` against the same `GraphRepository` protocol; shared contract test suite (entity upsert, relationship upsert, referential integrity, traversal, subgraph, search, pagination, metrics, delete/reindex, transaction rollback); factory wiring extended; `Literal` widened only after each adapter passes the contract. Run live tests under `pytest -m integration` when env vars present.

---

## Epic 12: Build out API surface for graph CRUD and query operations

**Gap:** `backend/api/routers/graph.py` is 24 lines and exposes only `GET /graph/entities/{id}` for detail (uses pre-baked payload, not the live service). All real graph reads live under `/investigation/*` (`routers/investigation.py` — 115 lines), which exposes only entity, neighborhood, search. No relationship detail, no paginated list, no subgraph endpoint, no write endpoints (entity property edits, manual relationship add, KB-scoped delete). Frontend Investigation Workbench needs richer surfaces per architecture §8.3.

**Outcome:** decide query-only vs write-capable per route group; ship `GET /graph/relationships/{id}`, paginated `GET /graph/entities`, `POST /graph/subgraph`, `PATCH /graph/entities/{id}` (already exists at service level via `update_entity_properties`); RBAC role decisions per endpoint; OpenAPI schemas updated.

---

## Epic 13: Add graph query observability — metrics, traces, structured audit

**Gap:** `GraphService` and adapters emit no metrics or trace spans. `neo4j_adapter.py` has `logger = logging.getLogger(__name__)` but uses it only for schema-bootstrap warnings (line 102, 162). No counters for entities upserted, relationships upserted, unchanged objects, errors-by-operation; no query-duration histogram; no audit log line on writes/deletes. Cross-edge to `_observability.md`.

**Outcome:** module metrics (`chili_graph_*`) for op count/duration/errors; OpenTelemetry spans around repository calls and event publication; structured audit log for write/delete with KB id, scope, counts — no entity payloads logged.

---

## Epic 14: Add graph snapshot export/import for backup and migration

**Gap:** Nothing in `graph/` exports a portable snapshot. Analytics modules consume graph through bespoke in-memory adaptors; no backup workflow exists. Cross-edge to `_infra.md` (object-store snapshot location, schedule), `_observability.md` (snapshot job health). §14.2 future capabilities table is silent on this but it underpins the disaster-recovery story.

**Outcome:** `GraphSnapshot` model (kb_id, entities, relationships, schema_version, created_at, checksum); `export_snapshot(kb_id) -> ObjectStoreKey`; `restore_snapshot(snapshot, mode=replace|merge|validate_only)`; periodic snapshot trigger from `agent/coordinator.py`; checksum round-trip test.

---

## Epic 15: Add tenant-scoped graph access (per-tenant Neo4j DB or label scoping)

**Gap:** `Neo4jGraphRepository.__init__(database: str | None = None)` (`neo4j_adapter.py:117`) supports a single database. No per-tenant database routing, no tenant label predicate, no tenant filter on the kb-id composite index. Architecture §14.2 lists "Multi-tenancy: Tenant-isolated data, config, and KB namespaces" as medium priority post-auth. Cross-edge to `_multitenancy.md`, `_security.md`.

**Outcome:** decision recorded between (a) per-tenant Neo4j database, (b) `:Tenant_<id>` label prefix, (c) `tenant_id` property added to composite index `(tenant_id, knowledge_base_id, entity_id)`. Implementation guarded by tenancy feature flag; cross-tenant query attempts default-deny.

---

## Epic 16: Add backend-native graph metrics (degree distribution, components, PageRank)

**Gap:** `GraphService.compute_metrics` (`service.py:283`) computes only `entity_count`, `relationship_count`, `avg_degree`. `GraphMetrics` model (`graph/models.py:41`) has exactly those three fields. Adapter `count_entities`/`count_relationships` are the only metric primitives. No degree distribution, no top-degree, no isolated-entity count, no PageRank, no connected components — analytics and dashboard surfaces have to recompute these in Python.

**Outcome:** richer `GraphMetrics` (degree histogram bins, top-N by degree, isolated entity count, connected component count, optional centrality); expensive metrics gated by config; Neo4j uses Cypher aggregation (optional Graph Data Science only when configured); large-graph performance budget asserted in tests.

---

## Open Questions

1. Multi-tenancy isolation strategy (Epic 15) — per-database vs label-prefix vs property has very different cost/operational profiles. Defer decision to `_multitenancy.md` and let this epic follow whatever lands there, or pick here?
2. Schema migration framework (Epic 9) — roll our own `:_SchemaVersion` node vs adopt an existing tool (e.g. liquigraph)? Roll-our-own is consistent with the `2026-05-21-neo4j-graph-indexes-design.md` §2 stance.
3. API surface (Epic 12) — should write endpoints exist at all in `/graph` (consumer-facing) or stay agent-only? Today writes are pipeline-only via events; manual analyst edits are not in scope per current architecture.
4. Bulk-write benchmark floor (Epic 8) — is there an existing performance target in `docs/` or should this epic propose one based on representative claims-stream volume?
