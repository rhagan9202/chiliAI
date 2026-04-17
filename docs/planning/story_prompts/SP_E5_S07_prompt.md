# Story E5-S07: WebSocket hub — real-time alerts

## Story
As an analyst, I want to receive new alerts in real-time via WebSocket.

## Acceptance Criteria
1. `api/routers/ws.py` defines `WS /ws/alerts` accepting WebSocket.
2. `AlertCreatedEvent` → JSON message to connected clients.
3. Clients can filter: `{"subscribe": {"severity": ["high", "critical"]}}`.
4. Ping/pong every 30s.
5. Test: connect, receive alert, severity filter, disconnect.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E5-S01       |

## Target Files
- `backend/api/routers/ws.py` — new WebSocket router with `WS /ws/alerts`
- `backend/events/types.py` — add `AlertCreatedEvent` if not already present
- `backend/api/dependencies.py` — add dependency for alert event subscription if needed
- `backend/tests/api/test_ws_router.py` — WebSocket tests for connect, alert broadcast, severity filter, disconnect

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router pattern for structure reference
- `backend/events/types.py` — existing event types (`EventBase`, `KnowledgeBaseCreatedEvent`, etc.)
- `backend/events/protocols.py` — `EventBus` protocol for subscribing to events
- `backend/events/runtime.py` — event bus implementation details
- `backend/shared/types.py` — `Alert` model
- `backend/api/dependencies.py` — existing DI patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- Use FastAPI `WebSocket` class and `WebSocketDisconnect` exception
- The WebSocket endpoint manages a connection registry (set of active connections)
- `AlertCreatedEvent` should extend `EventBase` with `alert: Alert` payload, defined in `events/types.py`
- Client sends a subscribe message `{"subscribe": {"severity": ["high", "critical"]}}` to filter alerts — default is all severities
- Implement ping/pong keep-alive every 30 seconds to detect stale connections
- Use `asyncio.create_task` for background ping and event listener tasks per connection
- JSON message format to client: `{"type": "alert", "data": {alert fields...}}`
- Handle `WebSocketDisconnect` gracefully — remove from connection registry without raising

## What NOT To Do
- Do NOT implement pipeline status WebSocket — that is E5-S08
- Do NOT implement WebSocket authentication — that is a separate concern
- Do NOT use third-party WebSocket libraries — use FastAPI's built-in WebSocket support
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT implement alert persistence or storage — the WebSocket only forwards events
- Do NOT create a heavyweight pub/sub system — a simple in-process broadcast hub is sufficient for now

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
