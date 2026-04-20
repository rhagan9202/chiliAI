# Story E2-S04: Neo4j production graph adapter

## Story
As a platform operator, I want a Neo4j adapter implementing `GraphRepository`, so that the platform can persist graph data durably with Cypher query capabilities.

## Acceptance Criteria
1. `graph/adapters/neo4j_adapter.py` implements every `GraphRepository` method using the `neo4j` Python driver.
2. Connection pooling is configured via `GraphDbConfig.pool_size`.
3. `get_neighbors` uses variable-length Cypher path patterns for efficient traversal.
4. `upsert_entities` and `upsert_relationships` use `MERGE` statements for idempotency.
5. Integration test (marked `@pytest.mark.integration`) validates round-trip CRUD against a test Neo4j instance.
6. `neo4j` is listed as an optional dependency in `pyproject.toml` under `[project.optional-dependencies]`.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** L
- **Dependencies:** E2-S01, E1-S04

## Target Files
- `backend/graph/adapters/neo4j_adapter.py` — new file, Neo4j `GraphRepository` implementation
- `backend/graph/adapters/__init__.py` — export `Neo4jGraphRepository`
- `backend/pyproject.toml` — add `neo4j` to optional dependencies
- `backend/config/schema.py` — ensure `GraphDbConfig` includes `pool_size` if not already present
- `backend/tests/graph/test_neo4j_adapter.py` — new file, integration tests

## Reference Files to Read First
- `backend/graph/adapters/protocols.py` — `GraphRepository` protocol (after E2-S01)
- `backend/graph/adapters/in_memory.py` — reference adapter implementation pattern
- `backend/graph/models.py` — `SubgraphResult`, `GraphMetrics` (after E2-S01)
- `backend/graph/exceptions.py` — graph exception types
- `backend/shared/types.py` — `Entity`, `Relationship`
- `backend/config/schema.py` — `GraphDbConfig` and other config schemas
- `backend/pyproject.toml` — current dependency structure

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use `neo4j` driver >= 5.x
- **SECURITY: Parameterize ALL Cypher queries — NEVER interpolate entity IDs or user-supplied values into query strings**
- Use `MERGE` for upserts to guarantee idempotency
- Connection pooling must be configurable via `GraphDbConfig.pool_size`
- Variable-length Cypher path patterns for `get_neighbors` (e.g., `[:REL*1..depth]`)
- Integration tests can use `testcontainers` or skip if Neo4j is unavailable (`pytest.importorskip` / `skipUnless`)
- `neo4j` must be an optional dependency — adapter import must not fail if `neo4j` is not installed

## What NOT To Do
- Do NOT make `neo4j` a required dependency — it must be optional
- Do NOT hardcode connection strings — use config
- Do NOT use string interpolation/f-strings for Cypher query parameters
- Do NOT modify the `GraphRepository` protocol
- Do NOT add schema migration logic — that is out of scope
- Do NOT add retry/backoff logic — keep the adapter simple for now

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
