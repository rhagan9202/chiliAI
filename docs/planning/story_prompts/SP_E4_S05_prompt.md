# Story E4-S05: Retry count tracking with exponential backoff

## Story
As a platform operator, I want the worker coordinator to retry failed pipeline steps with exponential backoff and a configurable max retry count.

## Acceptance Criteria
1. The coordinator wraps each event handler with retry logic: max retries configurable (default 3), exponential backoff (1s, 2s, 4s).
2. Retry count is tracked per event (via `correlation_id` or event ID).
3. After max retries, the event is routed to the dead-letter queue.
4. Each retry attempt logs: event type, correlation_id, attempt number, delay, error message.
5. Unit test verifies: transient failure retries succeed on second attempt; permanent failure exhausts retries.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P1          |
| Size         | M           |
| Dependencies | None        |

## Target Files
- `backend/agent/coordinator.py` — add retry wrapper with exponential backoff around event handlers
- `backend/agent/models.py` — add retry configuration model (max retries, base delay, backoff multiplier) if needed
- `backend/tests/agent/test_coordinator.py` — tests for transient and permanent failure retry scenarios

## Reference Files to Read First
- `backend/agent/coordinator.py` — current handler dispatch logic
- `backend/agent/models.py` — existing agent models
- `backend/agent/exceptions.py` — existing exception types
- `backend/events/types.py` — `EventBase` with `correlation_id` and event ID fields
- `backend/events/protocols.py` — `EventBus` protocol (for DLQ routing after exhaustion)
- `backend/config/schema.py` — `DomainConfig` for retry configuration placement
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Retry configuration must be injectable/configurable, not hardcoded magic numbers
- Default values: max retries = 3, base delay = 1.0s, backoff multiplier = 2.0
- Use `asyncio.sleep` for backoff delays (not `time.sleep`) to keep the event loop responsive
- Retry tracking must be per-event, keyed by `correlation_id` or event ID
- Logging must use structured logging with event type, correlation_id, attempt number, delay, and error message
- After max retries, delegate to DLQ (the DLQ mechanism may be a no-op stub until E4-S04 is implemented)

## What NOT To Do
- Do not use `time.sleep` — use `asyncio.sleep` for non-blocking backoff
- Do not implement the full DLQ mechanism here — that is E4-S04; just call the DLQ interface (stub if needed)
- Do not retry indefinitely; always respect the configured max retry count
- Do not swallow or lose the original exception details during retries
- Do not add jitter unless explicitly requested — keep the backoff deterministic for testability
- Do not block the event loop during retry delays

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
