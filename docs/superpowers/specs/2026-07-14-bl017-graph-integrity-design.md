# BL-017 — Graph referential integrity + version/merge semantics (design)

> Status: approved by product owner 2026-07-14 (three scope rulings recorded below).
> Sprint: 2026-27 (this note is the pre-sprint hard gate for BL-017 implementation).
> Module stories: `graph.01` (referential integrity), `graph.02` (merge/version semantics) — `docs/backlog/graph.md`.
> Requirement: REQ-GRAPH-001.

## Problem

Relationship upserts write unchecked: the in-memory adapter stores dangling endpoints verbatim (`in_memory.py:41-50`), and Neo4j `MERGE` silently creates phantom endpoint nodes (`neo4j_adapter.py:226-228`), corrupting analytics, subgraph extraction, and evidence packs. `Entity.version` / `Relationship.version` are persisted but blindly overwritten (`neo4j_adapter.py:176,188`); bulk upsert replaces the property blob wholesale, so replays and concurrent writers silently discard state. `graph/service.py:29` and `in_memory.py:21-23` carry the standing production TODOs.

## Product-owner rulings (2026-07-14)

1. **Doc-path integrity failure fails the document** — `GraphIntegrityError` is a permanent error surfaced through BL-041's per-document failure machinery, not a silent drop.
2. **Records flow runs strict from day one** — `create_placeholders` exists only as an explicit per-call escape hatch.
3. **Version-conflict detection is pipeline-internal in v1** — no API contract or frontend surface; the mechanism ships tested but unarmed (`expected_version=None` everywhere in the pipeline).

## Design

### 1. Referential integrity (graph.01)

The adapter-level invariant is **graph existence**, not payload existence (the extraction validator already rejects in-payload dangles — `shared/types.py::validate_relationship` via `ingestion/validator.py` — so the adapter check is defense-in-depth on the document path and the primary guard on the records path, where relationships legitimately reference entities from earlier batches).

- `upsert_relationships` collects the batch's distinct endpoint IDs and runs **one batched existence lookup** before writing: dict lookups in-memory; a single `UNWIND $ids AS id MATCH …` round-trip in Neo4j. This bounds the hot-path cost at one extra query per batch (sprint risk R-2); before/after cost is measurable via BL-043's `ingestion_stage` `duration_ms` logs.
- Strict mode switches the Neo4j endpoint clauses `MERGE` → `MATCH`, making phantom nodes impossible.
- `graph/exceptions.py` gains `GraphIntegrityError(GraphPersistenceError)` with `knowledge_base_id`, `missing_entity_ids: list[str]`, `relationship_ids: list[str]` — every dangling reference in the batch is reported, not just the first.
- `GraphService` exposes `integrity_mode: Literal["strict", "create_placeholders"]`, default `"strict"` on **both** `upsert_task` and `upsert_records_graph`. `create_placeholders` preserves today's behavior for explicit opt-in only.
- Because entities are upserted before relationships within a task/batch, in-payload references always pass strict mode; only genuinely-missing endpoints fail.

### 2. Failure semantics

- **Document path**: `GraphIntegrityError` chains inside `BatchUpsertError` (per graph.01 AC). The coordinator classifies it as **permanent** (same classification as the a60d19c permanent/transient split) → per-document `DocumentsFailedEvent` → the document surfaces `FAILED` with the missing-endpoint reason in the BL-041 status projection. One bad document does not poison its batch (tracker semantics fixed 2026-07-14).
- **Records path**: the failing batch raises with the chained integrity error and lands in the DLQ with a clear reason. Records have no per-document status surface — recorded as existing behavior, not new scope.

### 3. Merge semantics (graph.02)

Resolves the story's internal contradiction ("deep-merges per the `update_entity_properties` pattern" — that pattern is shallow):

- `merge_properties` (new default) is a **shallow top-level-key merge**, exactly the `update_entity_properties` pattern (`in_memory.py:77-80`): keys present in the payload overwrite — **including explicit nulls** — and keys absent from the payload are preserved. Nested dict values replace wholesale; there is no recursive deep-merge.
- `replace_properties` preserves today's wholesale overwrite.
- Relationship properties get identical treatment.
- Non-property fields (e.g. `type`): payload wins, except platform-owned fields (below).

### 4. Version semantics (graph.02)

`version` is already a **platform-owned field** (`shared/types.py:198`) — writers never control it:

- Adapters **ignore incoming `version` on upsert and own the counter**: stored `version` increments by 1 only on *effective change* — the post-merge normalized properties or `type` differ from the stored row. Idempotent replay of an identical payload never bumps `version` (the graph.02 AC's no-op guarantee, delivered without pulling in graph.03's broader scope).
- `expected_version`, when set, is a **per-entity compare** against the stored value before writing; a mismatch raises `GraphVersionConflictError(GraphPersistenceError)` with `entity_id`, `expected_version`, `actual_version`, and aborts that chunk's transaction (writes nothing — chunked writes already run per-transaction in `GraphService`).
- In v1 the pipeline always passes `expected_version=None`: ingestion is single-writer per KB (`_kb_busy`), so v1 conflicts concern replays, not concurrent humans. The mechanism ships fully tested but unarmed (ruling 3).

### 5. Plumbing

- `graph/models.py`: `GraphUpsertOptions(merge_mode: Literal["merge_properties", "replace_properties"] = "merge_properties", expected_version: int | None = None)`.
- `GraphRepository.upsert_entities` / `upsert_relationships` (in `graph/adapters/protocols.py`) accept `options: GraphUpsertOptions` (defaulted, so existing call sites keep compiling).
- `GraphBuildTask` gains `upsert_options: GraphUpsertOptions | None`; `GraphService.upsert_task` and `upsert_records_graph` propagate options and `integrity_mode`.
- **No API contract changes, no frontend work** (ruling 3) — no OpenAPI regen needed.

### 6. Housekeeping

- **Prerequisite cleanup (PM note)**: `graph.01` lists `[shared.01, _observability.02]` and `graph.02` lists `[shared.01]` — mislabeled (shared.01 = Alert.severity literal; _observability.02 = correlation-ID middleware; neither gates graph work). Reduced to `[]` alongside this note, following the BL-019 prereq-cleanup precedent (2026-06-23).
- **Out of scope, named explicitly**: retroactive cleanup of historic phantom nodes (one-off operator script if ever needed); API/frontend surface for `expected_version` (follow-on story); graph.03's broader idempotency/change-detection scope beyond no-bump-on-no-op; any CRDT / multi-writer / audit-history machinery.

### 7. Testing

- **Unit (both adapters)**: strict rejection with exact `missing_entity_ids` reporting; `create_placeholders` preserves legacy behavior; merge vs replace; explicit-null overwrite; version-conflict detection; no-op replay does not bump `version`.
- **Integration (live Neo4j, `-m integration`)**: strict-mode upsert of a relationship with a missing target creates **no** phantom node.
- **Full-stack (live, in-sprint per sprint R-5)**: re-ingest the same document twice → document ready, stored `version` unchanged; a batch containing a dangling-endpoint defect → that document `FAILED` with the integrity reason, sibling documents unaffected.
- Gates: pyright --strict clean; pytest ≥ 85% on `backend/graph/`.

## Code touch points

`graph/exceptions.py`, `graph/models.py`, `graph/adapters/protocols.py`, `graph/adapters/in_memory.py`, `graph/adapters/neo4j_adapter.py`, `graph/service.py`, `graph/service_models.py`, `agent/coordinator.py` (permanent-error classification for `GraphIntegrityError`), `backend/tests/graph/`, `backend/tests/agent/` (failure-path coverage), `docs/backlog/graph.md` (prereq cleanup).
