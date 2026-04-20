# Story E2-S06: Batch chunking for large graph upserts

## Story
As a platform developer, I want `GraphService.upsert_task` to split large entity/relationship lists into configurable batch sizes.

## Acceptance Criteria
1. `GraphService` accepts a `batch_size: int = 500` constructor parameter.
2. Entities and relationships are chunked into batches of `batch_size` and upserted sequentially, each in its own transaction.
3. If a batch fails, an error is raised with the count of successfully upserted entities before the failure.
4. Test with 1500 entities and batch_size=500 verifies three batches execute.

## Priority / Size / Dependencies
- **Priority:** P2
- **Size:** S
- **Dependencies:** E2-S05

## Target Files
- `backend/graph/service.py` — add `batch_size` parameter, implement chunked upsert logic
- `backend/graph/exceptions.py` — add `BatchUpsertError` (or similar) with partial-success metadata
- `backend/tests/graph/test_service.py` — add batch chunking tests

## Reference Files to Read First
- `backend/graph/service.py` — current `GraphService` and `upsert_task` (after E2-S05 transaction changes)
- `backend/graph/protocols.py` — `GraphServiceProtocol`
- `backend/graph/exceptions.py` — existing exception types
- `backend/graph/adapters/protocols.py` — `GraphRepository.transaction` (after E2-S05)
- `backend/tests/graph/test_service.py` — existing service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Each batch executes in its own transaction — a batch failure does NOT roll back previously committed batches
- The error raised on batch failure must include how many entities/relationships were successfully upserted before the failure
- Use simple list slicing for chunking — no external utilities needed
- `batch_size` default of 500 should be a constructor parameter, not a class constant

## What NOT To Do
- Do NOT add parallel/concurrent batch execution — batches run sequentially
- Do NOT add retry logic for failed batches
- Do NOT change the `GraphServiceProtocol` — batch_size is an implementation detail of `GraphService`
- Do NOT add batch_size to config schema — it is a constructor parameter only
- Do NOT roll back successful batches when a later batch fails — each batch is independently committed

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
