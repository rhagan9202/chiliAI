# Story E16-S01: AgentServiceProtocol — workflow lifecycle methods (get_status, list, cancel)

## Story
As a platform developer, I want `AgentServiceProtocol` and `AgentService` to expose `get_workflow_status()`, `list_workflows()`, and `cancel_workflow()` so that the API layer and operators can observe and control in-flight pipelines.

## Acceptance Criteria
1. `agent/protocols.py` adds to `AgentServiceProtocol`:
   - `get_workflow_status(workflow_id: str) -> WorkflowRun`
   - `list_workflows(kb_id: str, *, limit: int = 20, offset: int = 0) -> list[WorkflowRun]`
   - `cancel_workflow(workflow_id: str) -> None`
2. `agent/service.py` implements all three methods:
   - `get_workflow_status` delegates to `run_store.get_run()`; raises `WorkflowNotFoundError` if not found.
   - `list_workflows` delegates to `run_store.list_runs()` (see E16-S02).
   - `cancel_workflow` loads the run, sets `status = "cancelled"`, and persists via `run_store.save_run()`.
3. `agent/exceptions.py` adds `WorkflowNotFoundError`.
4. Unit tests cover: get existing run, get non-existent raises, list with limit/offset, cancel updates status.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E16-S02      |

## Target Files
- `backend/agent/protocols.py` — add lifecycle methods to `AgentServiceProtocol`
- `backend/agent/service.py` — implement `get_workflow_status`, `list_workflows`, `cancel_workflow`
- `backend/agent/exceptions.py` — add `WorkflowNotFoundError`
- `backend/tests/agent/test_service.py` — add lifecycle method tests

## Reference Files to Read First
- `backend/agent/protocols.py` — current `AgentServiceProtocol`
- `backend/agent/service.py` — current `AgentService`
- `backend/agent/models.py` — `WorkflowRun`, `WorkflowSubmissionRequest`
- `backend/agent/adapters/protocols.py` — `WorkflowRunStoreProtocol` (post E16-S02)
- `backend/tests/agent/test_service.py` — existing agent service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `cancel_workflow` is a soft cancel — it marks the run as cancelled in the store; it does not interrupt a currently running coordinator handler
- `list_workflows` supports offset-based pagination; cursor-based pagination is a future story
- `WorkflowNotFoundError` must be a subclass of the existing agent exception base

## What NOT To Do
- Do not implement interrupt/kill of an in-flight coordinator handler
- Do not expose these methods over HTTP in this story — API wiring is a separate story
- Do not add async variants in this story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
