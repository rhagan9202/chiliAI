# Story E4-S04: Dead-letter queue handling for failed pipeline events

## Story
As a platform operator, I want events that fail processing after exhausting retries to be moved to a dead-letter stream.

## Acceptance Criteria
1. `events/protocols.py` adds a `publish_to_dlq(event, error_info)` method to the `EventBus` protocol.
2. The in-memory adapter records DLQ entries in a separate list accessible for testing.
3. The Redis Streams adapter publishes to a `{stream_name}.dlq` stream.
4. The coordinator wraps each handler in a try/except: on failure, the event + error details are sent to DLQ.
5. DLQ entries include: original event payload, error message, traceback, timestamp, retry count.
6. Unit test verifies a failing handler routes the event to DLQ after retries are exhausted.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P1          |
| Size         | M           |
| Dependencies | E4-S05      |

## Target Files
- `backend/events/protocols.py` — add `publish_to_dlq` method to `EventBus` protocol
- `backend/events/adapters/in_memory.py` — implement DLQ entry tracking in a separate list
- `backend/events/adapters/redis_streams.py` — implement DLQ publishing to `{stream_name}.dlq`
- `backend/agent/coordinator.py` — wrap handlers with try/except to route failures to DLQ
- `backend/tests/agent/test_coordinator.py` — test failing handler routes to DLQ
- `backend/tests/events/test_in_memory.py` — test in-memory DLQ recording

## Reference Files to Read First
- `backend/events/protocols.py` — current `EventBus` protocol definition
- `backend/events/adapters/in_memory.py` — current in-memory adapter implementation
- `backend/events/adapters/redis_streams.py` — current Redis Streams adapter implementation
- `backend/events/types.py` — `EventBase` and event type definitions
- `backend/agent/coordinator.py` — current handler registration and dispatch logic
- `backend/tests/agent/test_coordinator.py` — existing coordinator test patterns
- `backend/tests/events/test_in_memory.py` — existing event bus test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- DLQ entries must be structured data (not just raw strings) — include event payload, error message, traceback, timestamp, retry count
- The `publish_to_dlq` method must be part of the `EventBus` protocol so all adapters implement it
- The in-memory DLQ list must be easily accessible in tests (e.g., as a public attribute)
- The Redis DLQ stream naming convention is `{stream_name}.dlq`
- This story depends on E4-S05 (retry tracking) — the DLQ routing happens after retries are exhausted

## What NOT To Do
- Do not implement retry logic in this story — that is E4-S05; assume retry exhaustion is signaled
- Do not swallow exceptions silently; always route to DLQ with full error context
- Do not create a separate DLQ service or module — keep it within the event bus protocol
- Do not break existing event publishing or handler registration
- Do not use bare `except:` — catch specific exception types or `Exception`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=events tests/events/` >= 85% coverage for events module
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for agent module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
