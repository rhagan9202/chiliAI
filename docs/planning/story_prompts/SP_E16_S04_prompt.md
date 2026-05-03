# Story E16-S04: Coordinator per-event error isolation

## Story
As a platform developer, I want each event handler invocation in the coordinator to be wrapped in a try/except so that a single malformed event or crashing handler does not halt the entire worker loop.

## Acceptance Criteria
1. `agent/coordinator.py` wraps each call to `handle_event(event)` in a `try/except Exception` block.
2. On exception: the error is logged at `ERROR` level with the event type, event ID, and full traceback; the event is acknowledged (consumed) so it is not re-delivered infinitely; a `WorkflowRun` status update to `"failed"` is attempted if the event carries a `workflow_id`.
3. Each individual _handler registration_ call inside `_dispatch_event()` is also wrapped so a broken handler does not prevent other handlers for the same event from running.
4. Unit tests simulate a handler that raises and verify: loop continues, error is logged, event is consumed, second handler for same event still runs.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | None         |

## Target Files
- `backend/agent/coordinator.py` — add try/except to `handle_event()` and `_dispatch_event()`
- `backend/tests/agent/test_coordinator.py` — add error isolation tests

## Reference Files to Read First
- `backend/agent/coordinator.py` — current event loop, `handle_event()`, `_dispatch_event()`
- `backend/agent/models.py` — `WorkflowRun` and status values
- `backend/tests/agent/test_coordinator.py` — existing coordinator tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- The outer `handle_event` try/except must catch `BaseException` subclasses (not `Exception` only) to catch things like `KeyboardInterrupt` — but re-raise `KeyboardInterrupt` and `SystemExit` to preserve shutdown signal handling
- Log the full traceback using `logging.exception()` (not just `logging.error()`)
- The `WorkflowRun` status update failure must itself be caught and logged, not raised

## What NOT To Do
- Do not add dead-letter queue publishing here — that is E4-S04
- Do not retry failed events here — that is E4-S05
- Do not catch `KeyboardInterrupt` / `SystemExit` — re-raise them

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
