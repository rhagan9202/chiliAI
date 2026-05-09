# Story E16-S02: WorkflowRunStoreProtocol — list, delete, update + in-memory implementation

## Story
As a platform developer, I want the `WorkflowRunStoreProtocol` to support listing, deleting, and updating workflow runs so that the agent service can power workflow lifecycle management.

## Acceptance Criteria
1. `agent/adapters/protocols.py` adds to `WorkflowRunStoreProtocol`:
   - `list_runs(kb_id: str, *, limit: int = 20, offset: int = 0) -> list[WorkflowRun]`
   - `delete_run(workflow_id: str) -> None` — no-op if not found
   - `update_run(workflow_id: str, updates: dict[str, object]) -> WorkflowRun` — merges field updates and returns updated run
2. `InMemoryWorkflowRunStore` implements all three new methods.
3. Unit tests cover: list with pagination, list filtered by kb_id, delete existing, delete non-existent (no error), update status field.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/agent/adapters/protocols.py` — add `list_runs`, `delete_run`, `update_run` to protocol
- `backend/agent/adapters/in_memory.py` — implement new methods on `InMemoryWorkflowRunStore`
- `backend/tests/agent/test_adapters.py` — add tests for new store methods

## Reference Files to Read First
- `backend/agent/adapters/protocols.py` — current `WorkflowRunStoreProtocol`
- `backend/agent/adapters/in_memory.py` — current `InMemoryWorkflowRunStore`
- `backend/agent/models.py` — `WorkflowRun` model
- `backend/tests/agent/` — existing agent adapter tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `list_runs` must filter by `kb_id` and apply `limit`/`offset` in Python (no DB query optimization needed for in-memory)
- `update_run` must not allow changing `workflow_id` or `kb_id` through `updates`; ignore those keys if present
- `delete_run` is a soft delete for in-memory: remove from the store dict

## What NOT To Do
- Do not implement a PostgreSQL or Redis adapter here — production adapters are a future story
- Do not add cursor-based pagination — offset is sufficient for this story
- Do not make `update_run` accept a full `WorkflowRun` — dict-based partial update only

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
