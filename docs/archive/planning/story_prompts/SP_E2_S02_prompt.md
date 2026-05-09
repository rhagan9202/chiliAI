# Story E2-S02: Implement read/query methods on InMemoryGraphRepository

## Story
As a platform developer, I want the in-memory graph adapter to implement all query methods from the extended protocol, so that tests and local development can exercise the full graph surface without a database.

## Acceptance Criteria
1. `InMemoryGraphRepository` implements every method added in E2-S01.
2. `get_neighbors` performs a BFS up to `depth` hops, respecting `direction`.
3. `search_entities` does a case-insensitive substring match on entity properties.
4. `delete_entity` also removes relationships referencing the deleted entity.
5. Unit tests cover each method (happy path + edge cases: missing entity, empty graph, depth=0).
6. Coverage >= 85% for the graph module.

## Priority / Size / Dependencies
- **Priority:** P0
- **Size:** M
- **Dependencies:** E2-S01

## Target Files
- `backend/graph/adapters/in_memory.py` — implement all new `GraphRepository` methods
- `backend/tests/graph/test_in_memory_adapter.py` — add comprehensive tests for each new method

## Reference Files to Read First
- `backend/graph/adapters/in_memory.py` — current in-memory adapter (write-only)
- `backend/graph/adapters/protocols.py` — `GraphRepository` protocol (after E2-S01 changes)
- `backend/graph/models.py` — `SubgraphResult`, `GraphMetrics` (after E2-S01 changes)
- `backend/shared/types.py` — `Entity`, `Relationship` definitions
- `backend/graph/exceptions.py` — existing graph exceptions
- `backend/tests/graph/test_in_memory_adapter.py` — existing adapter tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The BFS implementation for `get_neighbors` must build an adjacency index on first access — use lazy indexing (build once, invalidate on mutation)
- `search_entities` must be case-insensitive substring match on entity property values (all string properties)
- `delete_entity` must cascade-remove all relationships where the entity appears as source or target
- All data stays in-memory — no persistence to disk

## What NOT To Do
- Do NOT use external graph libraries (networkx, igraph) — implement BFS directly
- Do NOT modify the protocol — that was done in E2-S01
- Do NOT add service-layer changes — that is E2-S03
- Do NOT add thread-safety mechanisms unless they already exist in the current adapter
- Do NOT change the constructor signature of `InMemoryGraphRepository`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
