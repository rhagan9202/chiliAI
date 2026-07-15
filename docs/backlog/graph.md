# graph backlog

> **Scope:** Graph DB protocol + adapters (in-memory, Neo4j; Memgraph/Neptune roadmap), dual-graph contract, schema/index lifecycle, subgraph queries, backup.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story graph.01: Enforce relationship referential integrity in production mode

**ID:** graph.01
**Status:** done
**Prerequisites:** []
<!-- PM prereq cleanup 2026-07-14 (BL-017 design note): [shared.01, _observability.02] were mislabeled — shared.01 = Alert.severity literal, _observability.02 = correlation-ID middleware; neither gates graph integrity. -->

**Unblocks:** [_multitenancy.07, graph.04, rag.01]
**Estimated size:** M
**Done:** 2026-07-14 · BL-017 (Sprint 2026-27) · `feat/sprint-2026-27-graph-integrity`

**As a** platform engineer responsible for graph correctness,
**I need** relationship upserts to reject dangling source/target endpoints in production mode,
**so that** silently-created placeholder nodes can no longer corrupt analytics, subgraph extraction, or evidence packs.

### Current State (shipped)
- `graph/exceptions.py` exports `GraphIntegrityError(GraphPersistenceError)` with `knowledge_base_id`, `missing_entity_ids: list[str]`, `relationship_ids: list[str]`.
- `InMemoryGraphRepository.upsert_relationships` (`backend/graph/adapters/in_memory.py`) verifies every relationship's `source_id`/`target_id` against `self._entities[knowledge_base_id]` before writing and raises `GraphIntegrityError` on any miss when `integrity_mode="strict"`.
- `Neo4jGraphRepository.upsert_relationships` (`backend/graph/adapters/neo4j_adapter.py`) reads both endpoint IDs first (`_read_existing_entity_ids`) and raises `GraphIntegrityError` on any miss, then writes via `MATCH (source) MATCH (target) MERGE (source)-[r]->(target)` — no more `MERGE`-created placeholder endpoint nodes.
- `GraphService.upsert_task` and `upsert_records_graph` catch the underlying exception and re-raise `BatchUpsertError(...) from exc`, so `BatchUpsertError.__cause__` is the `GraphIntegrityError` for callers to introspect.
- `agent.coordinator.handle_entities_validated` introspects `BatchUpsertError.__cause__`: a `GraphIntegrityError` fails only that document via `DocumentsFailedEvent` (BL-017 Task 7); any other cause re-raises to the retry/DLQ wrapper.
- `create_placeholders` remains a defined `integrity_mode` literal but has no adapter implementation — selecting it today skips the strict check with no placeholder-node fallback; this is out of scope for this story (documented in `backend/graph/README.md`).

### Acceptance Criteria
- [x] `graph/exceptions.py` exports a typed `GraphIntegrityError(GraphPersistenceError)` with fields `knowledge_base_id`, `missing_entity_ids: list[str]`, `relationship_ids: list[str]`.
- [x] `GraphRepository.upsert_relationships` contract (in `graph/adapters/protocols.py`) is updated to specify that endpoints must already exist; both `InMemoryGraphRepository` and `Neo4jGraphRepository` verify endpoint presence (Cypher uses `MATCH ... MATCH ...` instead of `MERGE`) and raise `GraphIntegrityError` when an endpoint is missing.
- [x] `GraphService` exposes an `integrity_mode: Literal["strict", "create_placeholders"]` option (default `"strict"`); `upsert_task` and `upsert_records_graph` propagate it. **Deviation:** `integrity_mode` is a field on `GraphUpsertOptions` (threaded through `GraphBuildTask.upsert_options`), not a separate `GraphService` keyword argument — one options object flows through both entry points and both adapters instead of two independently-plumbed parameters.
- [x] `BatchUpsertError` chains the underlying `GraphIntegrityError` so callers can introspect which endpoints were missing.
- [x] Pyright-strict clean; unit tests cover (a) strict-mode rejection on both adapters, (b) legacy `create_placeholders` mode preserves prior behavior, (c) `upsert_task` surfaces `GraphIntegrityError` and rolls back per `graph.04`.

### Verification
- `cd backend && pytest tests/graph -k integrity --cov=graph` green; coverage ≥ 85% on `backend/graph/`.
- Live Neo4j integration test under `pytest -m integration -k integrity` confirms placeholder nodes are NOT created on strict-mode upsert of a relationship with a missing target.

### Code touch points
- `backend/graph/exceptions.py` (modify)
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/tests/graph/test_in_memory.py` (modify)
- `backend/tests/graph/test_neo4j_adapter.py` (modify)
- `backend/tests/graph/test_service.py` (modify)

---

## Story graph.02: Merge/version semantics and optimistic conflict detection on upserts

**ID:** graph.02
**Status:** done
**Prerequisites:** []
<!-- PM prereq cleanup 2026-07-14 (BL-017 design note): [shared.01] was mislabeled — shared.01 = Alert.severity literal; it does not gate merge/version semantics. -->

**Unblocks:** [analytics.12, analytics.24, analytics.25, graph.03, rag.02]
**Estimated size:** M
**Done:** 2026-07-14 · BL-017 (Sprint 2026-27) · `feat/sprint-2026-27-graph-integrity`

**As a** records-pipeline maintainer,
**I need** entity upsert to merge properties and reject stale writes via `expected_version`,
**so that** concurrent writers cannot silently overwrite each other and replays do not regress the graph to older state.

### Current State (shipped)
- `graph/models.py` exports `GraphUpsertOptions(merge_mode: Literal["merge_properties", "replace_properties"] = "merge_properties", expected_version: int | None = None, integrity_mode: Literal["strict", "create_placeholders"] = "strict")`; `graph/exceptions.py` exports `GraphVersionConflictError(GraphPersistenceError)` with `entity_id`, `expected_version`, `actual_version`.
- `InMemoryGraphRepository.upsert_entities` / `upsert_relationships` and `Neo4jGraphRepository.upsert_entities` / `upsert_relationships` all accept `options: GraphUpsertOptions | None = None` and honor `merge_mode`, `expected_version`, and adapter-owned `version` bump-only-on-change semantics (a `metadata`-only or fully-identical replay leaves `version` untouched).
- `replace_properties` preserves the pre-BL-017 blind-overwrite; `merge_properties` (the new default) shallow-merges incoming `properties`/`metadata` over the stored record.
- `expected_version`, when set, is validated against the stored row before any write; a mismatch raises `GraphVersionConflictError` and the batch is left untouched.
- `GraphService.upsert_task` and `upsert_records_graph` plumb `GraphUpsertOptions` through; `GraphBuildTask.upsert_options: GraphUpsertOptions | None` carries it end to end from the records/document pipelines.

### Acceptance Criteria
- [x] `graph/models.py` exports `GraphUpsertOptions(merge_mode: Literal["merge_properties", "replace_properties"], expected_version: int | None)` and `graph/exceptions.py` exports `GraphVersionConflictError(GraphPersistenceError)` with `entity_id`, `expected_version`, `actual_version`.
- [x] `GraphRepository.upsert_entities` / `upsert_relationships` accept `options: GraphUpsertOptions = GraphUpsertOptions(merge_mode="merge_properties", expected_version=None)`; both adapters honor it.
- [x] `replace_properties` preserves current overwrite semantics; `merge_properties` (the new default) deep-merges per the `update_entity_properties` pattern. **Deviation:** the merge is **shallow** (top-level `properties`/`metadata` keys only), not a recursive deep-merge — sufficient for the flat dicts entities/relationships carry, and matches the existing `update_entity_properties` implementation pattern (documented in `backend/graph/README.md`).
- [x] When `expected_version` is set and the stored row's `version` differs, the adapter raises `GraphVersionConflictError` and writes nothing.
- [x] `GraphService.upsert_task` and `upsert_records_graph` plumb options through; `GraphBuildTask` gains `upsert_options: GraphUpsertOptions | None`.
- [x] Pyright-strict clean; unit tests cover merge vs replace, version-conflict detection on both adapters, and idempotent replay does not bump `version` when nothing changed (see `graph.03`).

### Verification
- `cd backend && pytest tests/graph -k 'merge or version_conflict' --cov=graph` green; coverage ≥ 85%.
- Manual: ingest a document twice with `merge_properties` and confirm Neo4j row's `version` does not increment on the no-op second run.

### Code touch points
- `backend/graph/models.py` (modify)
- `backend/graph/exceptions.py` (modify)
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/graph/service_models.py` (modify)
- `backend/tests/graph/` (modify)

---

## Story graph.03: Change detection and idempotent upsert receipts

**ID:** graph.03
**Status:** planned
**Prerequisites:** [graph.02]
**Unblocks:** [_observability.09, rag.08]
**Estimated size:** L

**As a** downstream consumer (embeddings, analytics, monitoring),
**I need** graph upserts to report created/updated/unchanged/deleted partitions and only publish `GraphUpdatedEvent` on real change,
**so that** document replays do not trigger redundant embedding regenerations or analytics recomputations.

### Current State
- `GraphService.upsert_task` (`backend/graph/service.py:49-121`) unconditionally writes the graph-update artifact (`service.py:75-88`) and publishes `GraphUpdatedEvent` (`service.py:103-120`) regardless of whether the upsert changed anything.
- `GraphUpsertResult` (`backend/graph/models.py:21-32`) carries only `upserted_entity_ids` / `upserted_relationship_ids`; there is no created/updated/unchanged partition.
- `Neo4jGraphRepository.upsert_entities` uses `MERGE ... ON CREATE SET ... SET ...` (`neo4j_adapter.py:181-189`) which makes it impossible for the caller to tell created from updated without a follow-up query.
- No content-fingerprint is computed for entities or relationships; an identical payload bumps `version` and republishes events every time.
- **PM prereq cleanup (2026-06-23):** prereq `events.02` ("Trim Redis streams with MAXLEN/XTRIM retention") was spurious — this is change-detection + conditional publishing, and `GraphUpdatedEvent` is already fully defined and published (`events/types.py:135`, `graph/service.py:103`). Stream trimming does not gate it. Edge dropped; the only real prerequisite is graph.02.

### Acceptance Criteria
- [ ] `Entity` / `Relationship` payload signature (stable hash of `(type, properties, source_id, target_id)`) computed once and stored as `content_hash` (new field on the persisted row, not on `shared.types.Entity`).
- [ ] `GraphRepository.upsert_entities` / `upsert_relationships` return a typed receipt distinguishing `created_ids`, `updated_ids`, `unchanged_ids` (plus `deleted_ids` where applicable); both adapters implement it.
- [ ] `GraphUpsertResult` extends to include the four partitions; `GraphBuildReceipt` mirrors them.
- [ ] `GraphService.upsert_task` skips publishing `GraphUpdatedEvent` when every object is `unchanged` (configurable via `publish_on_unchanged: bool = False`; defaults to off in production mode, on in audit mode).
- [ ] Object-store artifact write is still performed (the receipt is the durable lineage record), but its metadata reflects the partition counts.
- [ ] Pyright-strict clean; tests verify (a) first write creates, (b) identical replay reports all-unchanged and does not publish, (c) modified replay reports updated and publishes.

### Verification
- `cd backend && pytest tests/graph tests/agent -k 'change_detection or idempotent_upsert' --cov=graph` green.
- Manual: re-publish an identical `GraphBuildTask` twice; `redis-cli XLEN graph_updated_events` increments by 1, not 2.

### Code touch points
- `backend/graph/models.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/graph/service_models.py` (modify)
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/tests/graph/` (modify)

---

## Story graph.04: Task-scoped transactional atomicity for graph build tasks

**ID:** graph.04
**Status:** planned
**Prerequisites:** [graph.01]
**Unblocks:** [analytics.01, graph.08, graph.11, monitoring.03]
**Estimated size:** L

**As a** worker maintainer,
**I need** a graph-build task's entity and relationship batches to commit atomically (or roll back atomically) at task scope,
**so that** a mid-task failure cannot leave the graph with the first two batches committed and the third half-applied.

### Current State
- `GraphService._upsert_entities` opens a fresh `self._repository.transaction(task.knowledge_base_id)` inside the loop, per entity batch (`backend/graph/service.py:125-138`); each batch is its own transaction.
- `GraphService._upsert_relationships` does the same per relationship batch (`service.py:149-162`).
- `BatchUpsertError` reports `successful_entity_count` / `successful_relationship_count` (`graph/exceptions.py:14-28`) but the partial commits are NOT rolled back — the next replay sees a partially-written graph.
- `InMemoryGraphRepository._transaction_scope` (`in_memory.py:255-286`) snapshots entities, relationships, and adjacency indexes on enter and restores on exception — only the snapshot of the CURRENT batch, not the whole task.
- **Correction (2026-06-01):** `Neo4jGraphRepository.transaction` (`neo4j_adapter.py:164`) is **not** a no-op — it opens a real Neo4j transaction via `session.begin_transaction()` and commits/rolls back on exit (`neo4j_adapter.py:578`), with `_run_read`/`_run_write` routing through the active transaction (`neo4j_adapter.py:592`, `599`). Adapter-level atomicity already exists; the remaining gap is purely at **service scope** — the transaction is opened per *batch* inside the upsert loops (see the `service.py` bullets above), not once per task.

### Acceptance Criteria
- [ ] `GraphRepository.transaction(knowledge_base_id)` contract is clarified: it MUST commit all writes done inside the `with` block atomically, or roll them all back on exception.
- [ ] `Neo4jGraphRepository.transaction` opens a real Neo4j transaction (via `session.begin_transaction()`), keeps it open for the duration of the `with`, and commits/rolls back on exit; all repository write methods route through the active transaction when one is held.
- [ ] `InMemoryGraphRepository._transaction_scope` snapshots at task scope (entered once per task) and rolls back the full task on exception.
- [ ] `GraphService.upsert_task` and `upsert_records_graph` open ONE transaction per task that wraps both entity and relationship batches.
- [ ] When the adapter does not support task-scoped transactions, the service explicitly emits an `IngestionTransactionUnsupportedWarning` and falls back to a documented `partial_success` mode (no behavior regression on existing in-memory tests).
- [ ] Pyright-strict clean; tests cover both adapters: induce a failure in the 3rd batch and assert the graph is empty after rollback.

### Verification
- `cd backend && pytest tests/graph -k transaction --cov=graph` green; coverage ≥ 85%.
- Live Neo4j integration test under `pytest -m integration -k transaction_rollback` confirms `MATCH (e:Entity) RETURN count(e)` is unchanged after a forced mid-task failure.

### Code touch points
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/graph/exceptions.py` (modify)
- `backend/tests/graph/` (modify)

---

## Story graph.05: Filtered subgraph extraction for evidence packs

**ID:** graph.05
**Status:** planned
**Prerequisites:** [shared.01]
**Unblocks:** [analytics.10, analytics.16, frontend.01, frontend.15, graph.12, monitoring.06]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-21-dual-graph-contract-design.md, docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md

**As a** monitoring / analytics service assembling an evidence pack,
**I need** to fetch a single subgraph spanning a list of seed entity IDs (with cross-edges),
**so that** evidence-pack construction is one round-trip per alert instead of one neighborhood query per seed.

### Current State
- `GraphService`, `GraphServiceProtocol`, and `GraphRepository` now expose `get_subgraph(knowledge_base_id, seed_entity_ids, depth=1) -> SubgraphResult`.
- Both in-memory and Neo4j adapters implement the shipped method as a single-KB deduplicated union of seed neighborhoods; tests cover empty seeds, unknown seeds, KB scoping, and service delegation.
- Residual gap: the shipped method is not the richer contract requested here. It does not accept `knowledge_base_ids: list[str]`, `include_internal_relationships`, or `expansion_depth=0` seed-internal edge semantics.
- `SubgraphResult` (`graph/models.py`) remains the right return type.
- Neo4j composite index `(:Entity {knowledge_base_id, entity_id})` still supports efficient seed lookup.

### Acceptance Criteria
- [ ] `GraphServiceProtocol` and `GraphRepository` add `get_subgraph(knowledge_base_ids: list[str], entity_ids: list[str], *, include_internal_relationships: bool = True, expansion_depth: int = 0) -> SubgraphResult`.
- [ ] Multi-KB scope (matching the dual-graph contract) is honored by both adapters.
- [ ] `expansion_depth=0` returns exactly the seeded entities plus relationships whose source AND target are in the seed set; `expansion_depth>0` adds N-hop neighbors.
- [ ] Neo4j adapter uses one `UNWIND $entity_ids AS id MATCH (e:Entity {knowledge_base_id: ..., entity_id: id}) ...` round-trip and relies on the composite index.
- [ ] In-memory adapter implements the same semantics deterministically.
- [ ] Latency budget asserted in benchmark test: ≤ 200 entities returns < 500 ms p95 on the docker-compose Neo4j integration profile.
- [ ] Pyright-strict clean; unit tests cover (a) seeds-only mode, (b) `include_internal_relationships=False`, (c) `expansion_depth=1`, (d) multi-KB seed list spanning both KBs.

### Verification
- `cd backend && pytest tests/graph -k get_subgraph --cov=graph` green; coverage ≥ 85%.
- `cd backend && pytest -m integration tests/graph/test_neo4j_adapter.py -k subgraph_perf` asserts the p95 latency budget.

### Code touch points
- `backend/graph/protocols.py` (modify)
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/tests/graph/` (modify)

---

## Story graph.06: Relationship detail reads, pagination, and cursor stability

**ID:** graph.06
**Status:** planned
**Prerequisites:** [shared.01]
**Unblocks:** [analytics.03, analytics.04, api.01, graph.11, graph.12, graph.15]
**Estimated size:** L

**As a** Investigation Workbench user paging through a large KB,
**I need** `get_relationship` / paginated `list_entities` / paginated `list_relationships` with deterministic cursors,
**so that** the frontend can scroll without re-fetching the entire KB and without duplicates/gaps as writes land.

### Current State
- `GraphRepository`'s TODO (`backend/graph/adapters/protocols.py:16-22`) calls out missing `get_relationship(kb_id, relationship_id) -> Relationship | None` and missing pagination on `get_entities` / `get_relationships`.
- `get_entities` (`in_memory.py:52-53`, `neo4j_adapter.py:256-262`) and `get_relationships` (`in_memory.py:55-56`, `neo4j_adapter.py:264-272`) return full unbounded lists.
- `get_entities_by_type` has SKIP/LIMIT (`in_memory.py:142-157`, `neo4j_adapter.py:388-409`) but no cursor, no filters beyond type, and offset-based paging drifts on concurrent writes.
- `api/routers/graph.py` is 24 lines and exposes only `GET /graph/entities/{id}` — paginated list endpoints depend on this work.

### Acceptance Criteria
- [ ] `GraphRepository` adds `get_relationship(knowledge_base_ids: list[str], relationship_id: str) -> Relationship | None`; both adapters implement.
- [ ] `GraphRepository` adds `list_entities(knowledge_base_id, *, filters: EntityListFilters, cursor: str | None, limit: int) -> PaginatedEntities` and the relationship analog, with `EntityListFilters(types: list[str] | None, updated_since: datetime | None)`.
- [ ] Cursor is an opaque base64-encoded `(updated_at, entity_id)` tuple — deterministic ordering by `(updated_at ASC, entity_id ASC)` so newly inserted rows do not shift earlier pages.
- [ ] `GraphService` exposes `get_relationship`, `list_entities`, `list_relationships`; existing `get_entities` retained as a compatibility shim that returns the full list (documented as expensive).
- [ ] Pyright-strict clean; unit tests verify cursor stability when a write lands mid-scan on both adapters.

### Verification
- `cd backend && pytest tests/graph -k pagination --cov=graph` green; coverage ≥ 85%.
- Manual: page 5K entities on Neo4j integration profile with a writer running concurrently; assert no duplicate / missed rows.

### Code touch points
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/graph/service_models.py` (modify)
- `backend/graph/models.py` (modify)
- `backend/tests/graph/` (modify)

---

## Story graph.07: Improve entity search relevance, filters, and observability

**ID:** graph.07
**Status:** planned
**Prerequisites:** [_observability.02]
**Unblocks:** [graph.12, monitoring.02, monitoring.14]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md

**As a** RAG retrieval pipeline / Investigation Workbench search box,
**I need** `search_entities` to return scored hits with type filters, matched fields, and snippets,
**so that** results can be ranked, faceted, and explained instead of being plain unordered lists.

### Current State
- `InMemoryGraphRepository.search_entities` (`backend/graph/adapters/in_memory.py:159-182`) does a Python substring scan over string property values; output is `list[Entity]` with insertion-order ranking.
- `Neo4jGraphRepository.search_entities` (`backend/graph/adapters/neo4j_adapter.py:411-439`) now uses the `entity_properties_fulltext` index (commit `b0fcc38`) and orders by Lucene `score DESC`, but discards the score in the return value and exposes no type filter or matched-field detail.
- `GraphService.search_entities` (`backend/graph/service.py:260-281`) passes `query` straight through and offers only `limit` / `offset`, dropping the underlying score.
- No metric or trace span around search.

### Acceptance Criteria
- [ ] New `EntitySearchHit` model in `graph/models.py` with `entity: Entity`, `score: float`, `matched_fields: list[str]`, `snippet: str | None`.
- [ ] `GraphRepository.search_entities` returns `list[EntitySearchHit]`; both adapters populate score (in-memory uses a deterministic substring-position rank; Neo4j uses Lucene score).
- [ ] `GraphService.search_entities` accepts `types: list[str] | None`, `properties: dict[str, str] | None` (exact-match property filters), returns `EntitySearchResult(hits, next_cursor, total)`.
- [ ] Neo4j query layers the type filter and property filters into the existing `CALL db.index.fulltext.queryNodes` `WHERE` clause.
- [ ] Pyright-strict clean; unit tests cover (a) score ordering on both adapters, (b) type filter narrows results, (c) `matched_fields` is populated correctly.

### Verification
- `cd backend && pytest tests/graph -k search --cov=graph` green; coverage ≥ 85%.
- Hit `POST /investigation/search` in the running stack, confirm response includes `score` and `matched_fields`.

### Code touch points
- `backend/graph/models.py` (modify)
- `backend/graph/service_models.py` (modify)
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/tests/graph/` (modify)

---

## Story graph.08: Bulk-write throughput — UNWIND tuning and adapter benchmarks

**ID:** graph.08
**Status:** planned
**Prerequisites:** [graph.04]
**Unblocks:** [api.01]
**Estimated size:** M

**As a** records-pipeline operator running NPPES / DE-SynPUF loads,
**I need** documented Neo4j throughput floors (entities/sec, relationships/sec) with a configurable batch size,
**so that** large-volume loads complete within the expected SLO and regressions are caught in CI.

### Current State
- `GraphService.batch_size = 500` is the only knob (`backend/graph/service.py:39`), shared between entity and relationship batches.
- `Neo4jGraphRepository.upsert_entities` round-trips a `properties_json` string per entity (`neo4j_adapter.py:168-179`); `_dump_json_property` (referenced near `neo4j_adapter.py:673`) calls `json.dumps` per row.
- No `tests/graph/test_perf.py`-style file exists; throughput is uninstrumented.
- Records pipeline (`backend/records/`) and claims stream consumers write large volumes; current behavior is unverified beyond functional correctness.

### Acceptance Criteria
- [ ] `GraphService` accepts separate `entity_batch_size` and `relationship_batch_size` (back-compat: `batch_size` applies to both when separate values are not supplied).
- [ ] New benchmark test at `backend/tests/graph/test_neo4j_perf.py` (marked `@pytest.mark.integration`) writes 10K entities + 10K relationships and asserts throughput floors of `≥ 5_000 entities/sec` and `≥ 3_000 relationships/sec` against the docker-compose Neo4j profile (constants documented in the test, easy to tune).
- [ ] In-memory adapter benchmark establishes a faster floor as a regression guard.
- [ ] `_dump_json_property` hot-path is profiled and either kept as-is or replaced with a streaming `orjson` call; the chosen rationale is in `backend/graph/README.md`.
- [ ] `docs/architecture.md` or `backend/graph/README.md` records the published throughput floor and the tuned batch size for the Medicare claims load profile.
- [ ] Pyright-strict clean.

### Verification
- `cd backend && pytest -m integration tests/graph/test_neo4j_perf.py` passes on the docker-compose Neo4j stack within the asserted throughput floor.
- `cd backend && pytest tests/graph --cov=graph` overall coverage ≥ 85%.

### Code touch points
- `backend/graph/service.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/tests/graph/test_neo4j_perf.py` (new)
- `backend/tests/graph/test_in_memory_perf.py` (new)
- `backend/graph/README.md` (modify)

---

## Story graph.09: Graph schema migrations and version metadata

**ID:** graph.09
**Status:** planned
**Prerequisites:** [graph.10]
**Unblocks:** [graph.14]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md

**As a** platform engineer evolving the Neo4j schema,
**I need** versioned, forward-only, idempotent schema migrations recorded in Neo4j,
**so that** I can add, alter, or remove indexes/constraints in lockstep with code without manual cypher.

### Current State
- `Neo4jGraphRepository._ensure_schema` (`backend/graph/adapters/neo4j_adapter.py:139-162`) only issues `CREATE ... IF NOT EXISTS` statements; there is no way to DROP or ALTER.
- No schema-version tracking node, no migrations registry, no partial-drift detection.
- The neo4j-indexes design spec at `docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md` §2 explicitly deferred a migration framework.
- Future work (dual-graph property indexes on NPI per architecture §7.4, additional analytics-driven indexes) must change the schema in lockstep with code.

### Acceptance Criteria
- [ ] `backend/graph/migrations/` package with `__init__.py` exposing `MIGRATIONS: list[GraphMigration]` ordered by integer version.
- [ ] `GraphMigration(version: int, name: str, apply: Callable[[Neo4jSessionProtocol], None])` Pydantic-or-dataclass type — forward-only, idempotent guidance documented.
- [ ] A `(:_SchemaVersion {key: "neo4j_graph", version: int, applied_at: datetime})` node records applied migrations; uniqueness constraint enforces single row.
- [ ] `Neo4jGraphRepository._ensure_schema` invokes pending migrations in order, in a transaction per migration, and updates `:_SchemaVersion` on success.
- [ ] The existing five `CREATE … IF NOT EXISTS` statements (`neo4j_adapter.py:141-156`) are encapsulated as `Migration 1`; subsequent additions land as new migration files.
- [ ] Pyright-strict clean; unit tests cover (a) fresh DB runs all migrations, (b) re-run is no-op, (c) partial state (version 1 applied, version 2 pending) applies only version 2, (d) failure mid-migration leaves `:_SchemaVersion` untouched.

### Verification
- `cd backend && pytest tests/graph -k migration --cov=graph` green; coverage ≥ 85%.
- `cd backend && pytest -m integration tests/graph/test_neo4j_adapter.py -k migration` confirms `MATCH (v:_SchemaVersion) RETURN v.version` returns the latest after boot.

### Code touch points
- `backend/graph/migrations/__init__.py` (new)
- `backend/graph/migrations/v001_initial_schema.py` (new)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/README.md` (modify)
- `backend/tests/graph/test_migrations.py` (new)
- `backend/tests/graph/test_neo4j_adapter.py` (modify)

---

## Story graph.10: Constraint/index lifecycle drift detection and `verify_schema`

**ID:** graph.10
**Status:** planned
**Prerequisites:** [_observability.02]
**Unblocks:** [agent.09, analytics.01, api.09, graph.09, graph.11, graph.15]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-21-neo4j-graph-indexes-design.md

**As a** SRE,
**I need** the graph adapter to verify, post-boot, that every declared constraint/index actually exists in Neo4j and to fail fast (or alert) on drift,
**so that** a silently-removed index or a partial bootstrap cannot degrade query performance without anyone noticing.

### Current State
- `Neo4jGraphRepository._ensure_schema` logs and continues on per-statement failure (`backend/graph/adapters/neo4j_adapter.py:158-162`) — the operator has no signal that the index actually exists post-apply.
- No `verify_schema()` / `SHOW CONSTRAINTS` / `SHOW INDEXES` introspection exists.
- No deploy-time probe exposes index health; a missing fulltext index degrades search to a slow scan without surfacing a 503.

### Acceptance Criteria
- [ ] `Neo4jGraphRepository.verify_schema() -> SchemaVerificationReport` enumerates `SHOW CONSTRAINTS` and `SHOW INDEXES`, compares against the declared set from the migrations registry (`graph.09`).
- [ ] `SchemaVerificationReport(missing_constraints: list[str], missing_indexes: list[str], extra_constraints: list[str], extra_indexes: list[str])`.
- [ ] `GraphDbConfig` adds `strict_schema_verification: bool = False`; when `True`, `Neo4jGraphRepository.__init__` raises `GraphSchemaDriftError` on any missing constraint/index after `_ensure_schema` runs.
- [ ] `GET /health/graph` (or extension to existing health endpoint owned by `api`) returns 503 when `verify_schema()` reports missing constraints/indexes.
- [ ] Cross-edge: `_observability.NN` consumes the report — emits `chili_graph_schema_drift{state="missing"}` gauge.
- [ ] Pyright-strict clean; unit tests fake `SHOW CONSTRAINTS` / `SHOW INDEXES` outputs and verify the diff logic.

### Verification
- `cd backend && pytest tests/graph -k verify_schema --cov=graph` green.
- Manual: drop an index in Neo4j Browser, restart the API, confirm `GET /health/graph` returns 503.

### Code touch points
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/models.py` (modify)
- `backend/graph/exceptions.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/api/routers/health.py` or equivalent (modify)
- `backend/tests/graph/test_neo4j_adapter.py` (modify)

---

## Story graph.11: Establish graph adapter contract suite

**ID:** graph.11
**Status:** planned
**Prerequisites:** [graph.04, graph.06, graph.10]
**Unblocks:** [graph.17]
**Estimated size:** L

### Narrative
As a platform engineer,
I want a reusable graph adapter contract suite,
so that additional graph backends can prove compatibility before being enabled.

### Current State
Current graph adapters are tested directly, but there is no shared backend-agnostic suite for Memgraph or Neptune work.

### Acceptance Criteria
- [ ] Define contract tests for node/edge upsert, traversal, evidence lookup, tenant context, and error behavior.
- [ ] Existing in-memory and Neo4j adapters pass the contract suite.
- [ ] Contract fixtures isolate backend setup and teardown.
- [ ] Documentation explains how new graph backends run the suite.

### Verification
- [ ] Run the graph adapter contract suite against existing adapters.
- [ ] Confirm failures identify the backend and contract case.

### Code touch points
- `backend/app/graph/**`
- `backend/tests/graph/**`
- `docs/wiki/modules/graph.md`

---
## Story graph.12: Build out the `/graph` API surface for CRUD and query operations

**ID:** graph.12
**Status:** planned
**Prerequisites:** [graph.05, graph.06, graph.07, api.29, _security.02]
**Unblocks:** []
**Estimated size:** L

**As a** Investigation Workbench frontend developer,
**I need** a richer `/graph` REST surface (relationship detail, paginated entity list, subgraph fetch, scored search),
**so that** UI flows can consume the graph service directly without routing every read through `/investigation/*`.

### Current State
- `backend/api/routers/graph.py` is 24 lines and exposes only `GET /graph/entities/{id}` (uses a pre-baked payload, not the live service).
- All real graph reads live under `/investigation/*` (`backend/api/routers/investigation.py` — 115 lines): entity detail, neighborhood, search.
- No relationship detail, no paginated list, no subgraph endpoint, no write endpoints (entity property edits, manual relationship add, KB-scoped delete) on `/graph`.
- `GraphService.update_entity_properties` exists at the service level (`graph/service.py:173-183`) but is not surfaced as an HTTP route.

### Acceptance Criteria
- [ ] Decision recorded in `docs/architecture.md` §8 or a short ADR: query-only `/graph` (analyst writes stay agent/pipeline-only) vs write-capable `/graph` with explicit RBAC. Default position: query-only for v1, with `PATCH /graph/entities/{id}` as the single sanctioned write surface.
- [ ] `GET /graph/relationships/{id}` (calls `GraphService.get_relationship`, returns shaped response).
- [ ] `GET /graph/entities?kb_id=&types=&cursor=&limit=` paginated list (calls `GraphService.list_entities` from `graph.06`).
- [ ] `GET /graph/relationships?kb_id=&cursor=&limit=` paginated list.
- [ ] `POST /graph/subgraph` (body: `kb_id`, `entity_ids`, `expansion_depth`) calls `GraphService.get_subgraph` from `graph.05`.
- [ ] `GET /graph/search?kb_id=&q=&types=&limit=` returns `EntitySearchResult` from `graph.07`.
- [ ] `PATCH /graph/entities/{id}` guarded by `require_role("analyst")`, body is `properties: dict[str, object]`.
- [ ] All endpoints call `resolve_kb_scope` (per the dual-graph contract) before invoking the service.
- [ ] OpenAPI schemas regenerated and reflect every new route; frontend can `npm run api:gen` cleanly.
- [ ] Pyright-strict clean; API tests cover each endpoint with 200 / 404 / 401 / 403 paths.

### Verification
- `cd backend && pytest tests/api/test_graph_router.py --cov=api.routers.graph` green; coverage ≥ 85%.
- Manual: hit each endpoint against the running stack with `httpie`; OpenAPI page at `/docs` shows them all.

### Code touch points
- `backend/api/routers/graph.py` (modify, substantial rewrite)
- `backend/api/dependencies.py` (modify)
- `backend/graph/service.py` (modify, plumb new method signatures)
- `backend/api/service_models/` (new graph-specific request/response shapes)
- `backend/tests/api/test_graph_router.py` (new or modify)
- `docs/architecture.md` (modify §8)

---

## Story graph.13: Graph query observability — metrics, traces, structured audit

**ID:** graph.13
**Status:** planned
**Prerequisites:** [_observability.02, _observability.03, _security.05]
**Unblocks:** []
**Estimated size:** M

**As an** on-call engineer diagnosing slow graph queries,
**I need** per-operation metrics, OpenTelemetry spans, and structured audit logs across the graph service and adapters,
**so that** I can pinpoint a regression to a query class and to a KB without spelunking through unstructured logs.

### Current State
- `GraphService` and adapters emit no metrics or trace spans.
- `Neo4jGraphRepository` has `logger = logging.getLogger(__name__)` (`backend/graph/adapters/neo4j_adapter.py:102`) but uses it only for schema-bootstrap warnings (`neo4j_adapter.py:162`).
- `InMemoryGraphRepository` has no logger at all.
- No counters for entities upserted / relationships upserted / unchanged objects / errors-by-operation; no query-duration histogram; no audit log on writes / deletes.
- Cross-edge: this story is the graph-shaped slice of `_observability.NN`; conventions for `chili_*` metric names and span attributes come from there.

### Acceptance Criteria
- [ ] Module metrics published via the shared registry from `_observability.NN`:
  - `chili_graph_op_total{operation, kb_id, status}` counter (entities_upserted, relationships_upserted, search, get_subgraph, get_entity, delete_*).
  - `chili_graph_op_duration_seconds{operation, kb_id}` histogram.
  - `chili_graph_objects_total{kind, partition}` counter where `partition ∈ {created, updated, unchanged, deleted}` (uses `graph.03` receipts).
- [ ] OpenTelemetry spans wrap every `GraphRepository` public method with span attributes `kb_id`, `operation`, `entity_count` / `relationship_count`.
- [ ] Structured JSON audit log line emitted for every write / delete: `kind`, `kb_id`, `actor` (when available via `api/middleware`), `scope`, `counts`. No entity payloads logged (PII safety per `_security.05`).
- [ ] `backend/graph/README.md` documents the metric / span / audit surface.
- [ ] Pyright-strict clean; unit tests assert metric labels are present after representative operations.

### Verification
- `cd backend && pytest tests/graph -k observability --cov=graph` green.
- Hit Prometheus scrape endpoint while running the stack; confirm `chili_graph_op_total` increases under load.
- Jaeger / OTLP collector receives `graph.upsert_entities` spans during ingestion.

### Code touch points
- `backend/graph/service.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/_telemetry.py` (new — module-local metric/span helpers wired to the shared registry)
- `backend/graph/README.md` (modify)
- `backend/tests/graph/test_telemetry.py` (new)

---

## Story graph.14: Graph snapshot export / import for backup and migration

**ID:** graph.14
**Status:** planned
**Prerequisites:** [graph.09, _infra.04, _observability.05]
**Unblocks:** [knowledgebases.09, knowledgebases.10]
**Estimated size:** L

**As a** platform operator preparing for disaster recovery,
**I need** a portable per-KB graph snapshot format with `export_snapshot` / `restore_snapshot` operations and a scheduled snapshot trigger,
**so that** a KB can be restored to a known-good state and migrated between backends without bespoke scripts.

### Current State
- Nothing in `backend/graph/` exports a portable snapshot. Analytics modules consume the graph through bespoke in-memory adapters; no backup workflow exists.
- Architecture §14.2 "Future capabilities" table (`docs/architecture.md:1350-1361`) is silent on graph snapshots but the disaster-recovery story for the Medicare exemplar requires it.
- Cross-edge: `_infra.04` owns the object-store snapshot location/schedule; `_observability.05` owns the snapshot-job health surface.

### Acceptance Criteria
- [ ] `graph/models.py` adds `GraphSnapshot(knowledge_base_id, schema_version, entities: list[Entity], relationships: list[Relationship], created_at, checksum)` with a Pydantic model dump format that is forward-compatible (versioned envelope).
- [ ] `GraphService.export_snapshot(kb_id) -> ObjectStoreKey` writes the snapshot as compressed JSONL or Parquet under `snapshots/graph/{kb_id}/{timestamp}.snapshot.jsonl.gz` using the `_infra.04` location convention.
- [ ] `GraphService.restore_snapshot(snapshot_key, mode: Literal["replace", "merge", "validate_only"])`:
  - `replace`: deletes KB then re-upserts.
  - `merge`: upserts on top of existing data using `merge_properties` mode (`graph.02`).
  - `validate_only`: parses the snapshot and asserts checksum + schema_version compatibility, performs no writes.
- [ ] Snapshot includes `schema_version` matched against the migrations registry from `graph.09`; a snapshot from a higher version is rejected.
- [ ] `agent/coordinator.py` exposes a periodic snapshot trigger fed by `_infra.04` schedule; success/failure surfaced as metric `chili_graph_snapshot_*` (per `_observability.05`).
- [ ] Round-trip test: export → checksum → delete KB → restore → assert entity/relationship sets equal.
- [ ] Pyright-strict clean.

### Verification
- `cd backend && pytest tests/graph -k snapshot --cov=graph` green; coverage ≥ 85%.
- Manual: trigger snapshot on KB-1 in dev, observe object in MinIO console, `restore_snapshot` into a fresh KB.

### Code touch points
- `backend/graph/models.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/graph/service_models.py` (modify)
- `backend/graph/snapshot.py` (new — serialization helpers)
- `backend/agent/coordinator.py` (modify — periodic trigger)
- `backend/tests/graph/test_snapshot.py` (new)

---

## Story graph.15: Define tenant-scoped graph isolation contract

**ID:** graph.15
**Status:** planned
**Prerequisites:** [graph.06, graph.10, knowledgebases.06]
**Unblocks:** [graph.19]
**Estimated size:** L

### Narrative
As a tenant administrator,
I want graph operations to carry explicit tenant scope,
so that knowledge graph data cannot leak across tenants.

### Current State
Knowledge bases have identity boundaries, but graph adapter APIs do not consistently model tenant isolation.

### Acceptance Criteria
- [ ] Tenant isolation decision is documented for labels/properties, databases, or namespaces.
- [ ] Graph protocol accepts tenant context for reads, writes, traversal, and deletes.
- [ ] Service-layer calls pass tenant context from knowledge base or request scope.
- [ ] Contract tests define expected cross-tenant isolation behavior.

### Verification
- [ ] Unit tests prove tenant context is required for tenant-sensitive operations.
- [ ] Contract tests fail if cross-tenant reads return another tenant's data.

### Code touch points
- `backend/app/graph/**`
- `backend/app/knowledgebases/**`
- `backend/tests/graph/**`

---
## Story graph.16: Backend-native graph metrics (degree distribution, components, PageRank)

**ID:** graph.16
**Status:** planned
**Prerequisites:** [analytics.32, _observability.02]
**Unblocks:** [analytics.18]
**Estimated size:** L

**As a** Dashboard and analytics consumer,
**I need** richer `GraphMetrics` (degree histogram, top-N degree, isolated entity count, connected component count, optional centrality scores),
**so that** the frontend and analytics pipelines do not recompute these by full graph scans in Python.

### Current State
- `GraphService.compute_metrics` (`backend/graph/service.py:283-298`) computes only `entity_count`, `relationship_count`, `avg_degree`.
- `GraphMetrics` model (`backend/graph/models.py:41-46`) has exactly those three fields.
- Adapter primitives `count_entities` / `count_relationships` (`in_memory.py:184-188`, `neo4j_adapter.py:441-453`) are the only metric building blocks.
- No degree distribution, no top-N by degree, no isolated-entity count, no PageRank, no connected components — analytics / dashboard surfaces have to recompute these.

### Acceptance Criteria
- [ ] `GraphMetrics` extended with `degree_histogram: dict[int, int]`, `top_degree_entities: list[tuple[str, int]]`, `isolated_entity_count: int`, `connected_component_count: int`, `centrality: GraphCentrality | None`.
- [ ] `GraphCentrality(top_pagerank: list[tuple[str, float]] | None)` — populated only when expensive metrics are enabled.
- [ ] `GraphDbConfig` adds `metrics_profile: Literal["basic", "extended", "centrality"] = "basic"`; `extended` adds histogram/top-N/isolated/components; `centrality` enables PageRank (requires Neo4j GDS plugin — soft-fails to `None` with a warning when GDS is unavailable).
- [ ] `Neo4jGraphRepository` implements all `extended` metrics via Cypher aggregation queries (single round-trip per metric class), no Python-side iteration.
- [ ] `InMemoryGraphRepository` implements every metric (the `centrality` path uses a simple PageRank implementation in pure Python — deterministic for tests).
- [ ] Performance budget asserted: `metrics_profile = extended` on a 50K-entity / 200K-relationship Neo4j integration fixture returns within 2 s p95.
- [ ] Cross-edge: `analytics.01` consumes the new metrics; `_observability.02` registers the resulting Prometheus gauges.
- [ ] Pyright-strict clean; unit tests cover the histogram/components on both adapters and gracefully-degrades-without-GDS on Neo4j.

### Verification
- `cd backend && pytest tests/graph -k metrics --cov=graph` green; coverage ≥ 85%.
- `pytest -m integration tests/graph/test_neo4j_adapter.py -k extended_metrics_perf` asserts the p95 budget.

### Code touch points
- `backend/graph/models.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/graph/adapters/protocols.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/graph/test_metrics.py` (new or modify)

## Story graph.17: Add Memgraph graph adapter

**ID:** graph.17
**Status:** planned
**Prerequisites:** [graph.11]
**Unblocks:** [graph.18]
**Estimated size:** L

### Narrative
As an operator,
I want Memgraph as a supported graph backend option,
so that deployments can choose a Cypher-compatible backend beyond Neo4j.

### Acceptance Criteria
- [ ] Memgraph adapter implements the graph protocol and passes the shared contract suite.
- [ ] Configuration selects Memgraph with connection settings and health checks.
- [ ] Documentation captures supported Memgraph versions and known differences from Neo4j.

### Verification
- [ ] Run graph contract tests against a Memgraph test container or documented substitute.
- [ ] Config tests prove Memgraph can be selected without changing callers.

### Code touch points
- `backend/app/graph/**`
- `backend/app/config/**`
- `backend/tests/graph/**`

---

## Story graph.18: Add Neptune graph adapter

**ID:** graph.18
**Status:** planned
**Prerequisites:** [graph.17]
**Unblocks:** [api.19, knowledgebases.11]
**Estimated size:** L

### Narrative
As an operator,
I want Amazon Neptune as a supported graph backend option,
so that AWS deployments can use a managed graph service.

### Acceptance Criteria
- [ ] Neptune adapter implements the graph protocol and passes applicable contract tests.
- [ ] Configuration selects Neptune with endpoint, auth, and traversal mode settings.
- [ ] Documentation captures supported Neptune mode, limitations, and deployment assumptions.

### Verification
- [ ] Run adapter contract tests with a Neptune-compatible fixture or documented integration environment.
- [ ] Config tests prove Neptune can be selected without changing callers.

### Code touch points
- `backend/app/graph/**`
- `backend/app/config/**`
- `backend/tests/graph/**`

---

## Story graph.19: Enforce tenant scope in in-memory and Neo4j graph adapters

**ID:** graph.19
**Status:** planned
**Prerequisites:** [graph.15]
**Unblocks:** [graph.20]
**Estimated size:** L

### Narrative
As a tenant administrator,
I want existing graph adapters to enforce tenant scope,
so that current deployments honor the tenant isolation contract.

### Acceptance Criteria
- [ ] In-memory adapter stores and filters graph records by tenant context.
- [ ] Neo4j adapter persists tenant labels/properties or database selection according to the isolation decision.
- [ ] Cross-tenant reads, traversals, and deletes are rejected or return empty results consistently.

### Verification
- [ ] Contract tests pass for tenant isolation on in-memory and Neo4j adapters.
- [ ] Regression tests prove one tenant cannot delete another tenant's graph records.

### Code touch points
- `backend/app/graph/**`
- `backend/tests/graph/**`

---

## Story graph.20: Add per-tenant graph migration and routing support

**ID:** graph.20
**Status:** planned
**Prerequisites:** [graph.19]
**Unblocks:** []
**Estimated size:** L

### Narrative
As a platform operator,
I want migration and routing support for tenant-scoped graph storage,
so that deployments can evolve from shared to isolated graph layouts safely.

### Acceptance Criteria
- [ ] Migration plan covers existing graph records and tenant ownership backfill.
- [ ] Graph service routes operations to the correct tenant storage boundary.
- [ ] Operational docs describe migration order, rollback limits, and verification queries.

### Verification
- [ ] Migration tests cover representative existing graph records.
- [ ] Integration tests prove tenant routing survives service restarts.

### Code touch points
- `backend/app/graph/**`
- `backend/app/db/**`
- `docs/operations/**`

---
