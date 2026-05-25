# Neo4j Graph Adapter — Composite Indexes and Constraints

## Goal

Stop every Neo4j read and write in the graph adapter from doing full label scans across the `:Entity` label. Today no `CREATE INDEX` or `CREATE CONSTRAINT` statements exist in `backend/graph/adapters/neo4j_adapter.py`, so every `MERGE`, `MATCH`, and neighborhood traversal scans all entities in the database regardless of `knowledge_base_id`. This is tolerable on synthetic DE-SynPUF samples (~50K rows) but becomes catastrophic once real CMS data and the dual-graph (policy KB + per-cycle claims KBs) approach are in play.

The fix is to issue the missing schema statements idempotently when the adapter starts up. It is a standalone, scoped piece of work that must land before the dual-graph protocol change makes the indexing gap a hard blocker.

## Current Context

`Neo4jGraphRepository` (`backend/graph/adapters/neo4j_adapter.py`) is the only Neo4j-backed implementation of `GraphRepository`. Every persistence path goes through one of these patterns:

- `MERGE (entity:Entity {knowledge_base_id: $kb, entity_id: row.entity_id})` — `upsert_entities`, runs per entity per batch.
- `MERGE (source)-[r:RELATES {knowledge_base_id: $kb, relationship_id: row.relationship_id}]->(target)` — `upsert_relationships`.
- `MATCH (entity:Entity {knowledge_base_id: $kb, entity_id: $id})` — `get_entity`, `update_entity_properties`, and the root match in `get_neighbors`.
- `MATCH (entity:Entity {knowledge_base_id: $kb})` — `get_entities` and `get_relationships`.
- Variable-length neighborhood traversal `(root)-[:RELATES*1..N]-(neighbor)` with a post-traversal `WHERE all(r IN relationships(path) WHERE r.knowledge_base_id = $kb)` filter — `get_neighbors`.

Neo4j is pinned to the `neo4j:5` image in both `docker-compose.yaml` and `docker-compose.dev.yaml`. The codebase does not pin a minor version of Neo4j 5.

The existing fake-driver unit test infrastructure in `backend/tests/graph/test_neo4j_adapter.py` captures every issued query in a `queries` list, which is what new assertions should hook into. Live-Neo4j integration tests run under `pytest -m integration`.

## Scope

In scope:

- Adding a schema-ensure step that issues composite-index and uniqueness statements idempotently when `Neo4jGraphRepository.__init__` runs.
- Tolerating schema-ensure failures (e.g. insufficient DDL permission) with a logged warning rather than aborting startup.
- Unit tests that verify the four CREATE statements are issued, that the schema-ensure is idempotent, and that a CREATE failure does not abort `__init__`.
- A short note in `backend/graph/README.md` documenting the schema invariants.

Out of scope (deferred to the dual-graph work):

- Cross-KB query signatures (changing `get_entity(kb_id, ...)` to `get_entity(kb_ids, ...)`).
- Domain-config-level auto-attach of a reference KB.
- A KB metadata table that links transactional KBs to reference KBs.
- Indexes on cross-KB join keys such as `npi` for providers — those are domain-shape-specific and belong with the dual-graph work.
- Any Neo4j Bolt-permissions/role/operator-permission work.

## Design

### 1. Schema statements

A `_ensure_schema` method on `Neo4jGraphRepository` issues four idempotent statements when the adapter is constructed:

```cypher
CREATE CONSTRAINT entity_kb_id_unique IF NOT EXISTS
FOR (e:Entity)
REQUIRE (e.knowledge_base_id, e.entity_id) IS UNIQUE;

CREATE INDEX entity_kb_id IF NOT EXISTS
FOR (e:Entity)
ON (e.knowledge_base_id);

CREATE INDEX rel_kb_id_relationship_id IF NOT EXISTS
FOR ()-[r:RELATES]-()
ON (r.knowledge_base_id, r.relationship_id);

CREATE INDEX rel_kb_id IF NOT EXISTS
FOR ()-[r:RELATES]-()
ON (r.knowledge_base_id);
```

Why this set, and why no relationship key constraint:

| Statement | Purpose | Notes |
|---|---|---|
| Entity composite **constraint** on `(knowledge_base_id, entity_id)` | Enforces the uniqueness invariant the code already assumes and provides the composite index that powers every entity `MERGE` and lookup. | Replaces a separate composite index — the constraint creates the index automatically. |
| Entity index on `(knowledge_base_id)` alone | Powers full-KB scans (`get_entities`, `get_relationships` root match). | The composite constraint can serve leading-column queries but an explicit single-column index removes planner ambiguity. |
| Relationship composite **index** on `(knowledge_base_id, relationship_id)` | Powers relationship `MERGE` and lookups. | A relationship key constraint would be cleaner but requires Neo4j 5.7+ (relationship key feature). The `neo4j:5` Docker tag does not pin a minor version, so we use an index instead. `MERGE` semantics already enforce uniqueness logically; we are only adding the index for performance. |
| Relationship index on `(knowledge_base_id)` | Powers the per-hop `WHERE r.knowledge_base_id = $kb` filter in the variable-length path traversal in `get_neighbors`. | Without it the planner cannot push the filter into the traversal and falls back to scanning every traversed relationship. |

All four statements use `IF NOT EXISTS`, so re-running them on an already-schemed database is a no-op.

### 2. When `_ensure_schema` runs

Called once at the end of `Neo4jGraphRepository.__init__`, after the driver is constructed. The session opened for the schema work uses the same `_session()` helper as every other write path, so it inherits the database configuration (`self._database`).

We do not use a migration framework, schema-versioning table, or Alembic-equivalent. The statements are idempotent and the schema is small enough that ensure-on-startup is the simplest correct approach.

### 3. Failure handling

Each statement runs in its own `try`/`except Neo4jError` block. On failure:

- The statement and the exception message are logged at `WARNING` level (using the existing `logging.getLogger(__name__)` instance for the module).
- The next statement is still attempted (statements are independent).
- `__init__` returns successfully.

Rationale: in dev the docker-compose Neo4j runs with admin rights and DDL succeeds; in prod the operator may have set up the database with restricted DDL permissions and provisioned the schema out-of-band. Hard-failing `__init__` would block deployments for an issue that is diagnosable from logs and does not affect correctness of subsequent queries (queries still work without indexes, just slowly).

Logging at `WARNING` is loud enough to be noticed in normal operation but does not flood logs on healthy startups.

### 4. Concurrency

Multiple worker processes (the API + the agent worker, both running `chili-api`/`chili-worker` containers) may construct `Neo4jGraphRepository` instances near-simultaneously at boot. `IF NOT EXISTS` makes the schema statements safe under concurrent execution: Neo4j serializes the schema operations and the second caller observes the index already exists.

### 5. Logging

Add `import logging` and a module-level `logger = logging.getLogger(__name__)` near the top of `neo4j_adapter.py` — the adapter does not currently have a logger. Use `logger.warning("Failed to ensure Neo4j schema: %s — %s", stmt, exc)` for schema-statement failures. No other log level introductions for this work.

### 6. Tests

Unit tests, using the existing `_FakeGraphDatabase`/`_FakeDriver` fixtures in `backend/tests/graph/test_neo4j_adapter.py`:

- **`test_init_issues_schema_statements`** — constructing `Neo4jGraphRepository` issues the four expected `CREATE ... IF NOT EXISTS` statements (matched by substring on the statement text). Verifies all four are present in the fake driver's captured `queries`.
- **`test_init_schema_is_idempotent_in_test_double`** — constructing the adapter twice with the same fake driver issues the schema statements twice without error (idempotency is enforced by `IF NOT EXISTS` in real Neo4j; the test confirms our code doesn't gate or guard the call).
- **`test_init_tolerates_schema_failure`** — configure the fake session to raise `Neo4jError` for the first schema statement; assert `__init__` returns successfully, the warning is emitted (capture via `caplog`), and the subsequent statements are still attempted.

No new integration test is required — the integration suite already validates that real reads and writes work, and the schema statements use `IF NOT EXISTS` so they cannot create regressions.

### 7. Documentation

Add a short "Schema invariants" section to `backend/graph/README.md` listing the four CREATE statements, calling out that `Neo4jGraphRepository.__init__` issues them at startup, and noting that the constraint enforces the `(knowledge_base_id, entity_id)` uniqueness invariant the rest of the code assumes.

### 8. Files touched

| File | Change |
|---|---|
| `backend/graph/adapters/neo4j_adapter.py` | Add module logger, add `_ensure_schema`, invoke from `__init__` |
| `backend/tests/graph/test_neo4j_adapter.py` | Three new tests covering issuance, idempotency, failure tolerance |
| `backend/graph/README.md` | Schema-invariants section |

## Success Criteria

- Starting any process that constructs `Neo4jGraphRepository` causes the four `CREATE ... IF NOT EXISTS` statements to be issued to Neo4j.
- A schema-statement failure produces a `WARNING` log line and does not abort `__init__`.
- Re-constructing the adapter against an already-schemed database is a no-op (no failures, no duplicate indexes).
- Subsequent entity and relationship reads continue to return the same results as today (no behavioural change — only a performance change).
- `pyright --strict` clean, `pytest --cov` ≥ 85% in `backend/graph/`, ruff clean. All existing tests continue to pass.
- The four expected schema statements are observable in the Neo4j logs on first boot of a fresh database (manual verification, not automated).
