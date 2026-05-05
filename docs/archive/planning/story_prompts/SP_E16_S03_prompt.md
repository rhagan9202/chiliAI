# Story E16-S03: Agent service idempotency key and compensating transaction

## Story
As a platform developer, I want `AgentService.start_workflow()` to accept an idempotency key so that duplicate submissions (e.g., retried API calls) return the existing run without re-starting the pipeline, and to use a compensating transaction if the event publish step fails after the run is persisted.

## Acceptance Criteria
1. `agent/service_models.py` adds `idempotency_key: str | None = None` to `WorkflowSubmissionRequest`.
2. `agent/service.py` checks for an existing run with the same `idempotency_key` before persisting a new one; if found, returns the existing `WorkflowSubmissionResponse` immediately.
3. If `event_bus.publish()` fails after the run is persisted, the service attempts to delete the run (`run_store.delete_run(workflow_id)`) as a compensating transaction and re-raises the event bus exception.
4. `WorkflowRun` stores `idempotency_key: str | None = None` for lookup.
5. Unit tests cover: first submission returns new run, duplicate key returns same run ID, event publish failure triggers compensation (run deleted).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E16-S02      |

## Target Files
- `backend/agent/service_models.py` — add `idempotency_key` to `WorkflowSubmissionRequest`
- `backend/agent/models.py` — add `idempotency_key` to `WorkflowRun`
- `backend/agent/service.py` — add idempotency check and compensating transaction
- `backend/agent/adapters/in_memory.py` — extend list/lookup to support idempotency key index
- `backend/tests/agent/test_service.py` — add idempotency and compensation tests

## Reference Files to Read First
- `backend/agent/service.py` — current `AgentService.start_workflow()`
- `backend/agent/service_models.py` — `WorkflowSubmissionRequest`
- `backend/agent/models.py` — `WorkflowRun`
- `backend/agent/adapters/in_memory.py` — `InMemoryWorkflowRunStore`
- `backend/tests/agent/test_service.py` — existing agent service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Idempotency check is a best-effort in-memory lookup; it is not transactional across processes
- Compensating transaction must not swallow the original event bus exception
- `idempotency_key` lookup is O(n) in the in-memory store; a key index is acceptable

## What NOT To Do
- Do not implement distributed locking for idempotency — single-process only in this story
- Do not change the event bus publish signature
- Do not suppress the event bus exception after compensation

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
