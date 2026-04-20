# Story E2-S05: Add transaction semantics to graph upsert

## Story
As a platform developer, I want entity and relationship upserts within a single `GraphBuildTask` to execute atomically.

## Acceptance Criteria
1. `GraphRepository` protocol adds a context-manager method `transaction(kb_id) -> AbstractContextManager` (or equivalent).
2. `GraphService.upsert_task` wraps entity + relationship upserts in a single transaction scope.
3. If relationship upsert fails, entity upsert is rolled back.
4. In-memory adapter implements transaction via a snapshot-and-restore mechanism.
5. Neo4j adapter delegates to a driver-level transaction.
6. Test verifies rollback: inject a failure during relationship upsert and confirm entities are not persisted.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** M
- **Dependencies:** E2-S02, E2-S04

## Target Files
- `backend/graph/adapters/protocols.py` — add `transaction` context-manager method to `GraphRepository`
- `backend/graph/adapters/in_memory.py` — implement transaction via snapshot-and-restore
- `backend/graph/adapters/neo4j_adapter.py` — implement transaction via Neo4j driver transaction
- `backend/graph/service.py` — wrap `upsert_task` in transaction scope
- `backend/tests/graph/test_in_memory_adapter.py` — add rollback/commit tests
- `backend/tests/graph/test_service.py` — add transaction delegation tests
- `backend/tests/graph/test_neo4j_adapter.py` — add transaction integration test

## Reference Files to Read First
- `backend/graph/adapters/protocols.py` — current `GraphRepository` protocol (after E2-S01)
- `backend/graph/adapters/in_memory.py` — current in-memory adapter (after E2-S02)
- `backend/graph/adapters/neo4j_adapter.py` — Neo4j adapter (after E2-S04)
- `backend/graph/service.py` — current `GraphService.upsert_task` implementation
- `backend/graph/exceptions.py` — existing exception types
- `backend/tests/graph/test_in_memory_adapter.py` — existing adapter tests
- `backend/tests/graph/test_service.py` — existing service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- For the in-memory adapter, use `copy.deepcopy` to snapshot affected buckets before the operation and restore on failure
- The `transaction` method should return a context manager (use `contextlib.contextmanager` or implement `__aenter__`/`__aexit__` if async)
- Transaction scope must cover both entity and relationship upserts within a single `upsert_task` call
- Neo4j transaction must delegate to the driver's native transaction management

## What NOT To Do
- Do NOT add distributed transaction support — single-adapter transactions only
- Do NOT add savepoint/nested transaction support
- Do NOT change the `upsert_task` public signature — transaction is internal
- Do NOT add async transaction support unless the existing adapter is already async
- Do NOT deep-copy the entire repository state — only snapshot the affected kb_id buckets

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
