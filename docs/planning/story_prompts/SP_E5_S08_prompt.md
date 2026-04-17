# Story E5-S08: WebSocket hub — pipeline status

## Story
As an analyst, I want to see pipeline stage progress in real-time via WebSocket.

## Acceptance Criteria
1. `WS /ws/pipeline` accepts WebSocket.
2. Pipeline events forwarded to clients scoped by `knowledge_base_id`.
3. Clients: `{"subscribe": {"kb_id": "..."}}`.
4. Each message: `event_type`, `knowledge_base_id`, `progress`, `timestamp`.
5. Test: scoped subscription receives only matching events.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E5-S07       |

## Target Files
- `backend/api/routers/ws.py` — add `WS /ws/pipeline` endpoint
- `backend/events/types.py` — add `PipelineProgressEvent` if not already present
- `backend/tests/api/test_ws_router.py` — add pipeline WebSocket tests

## Reference Files to Read First
- `backend/api/routers/ws.py` — the WebSocket router from E5-S07 (connection registry, ping/pong patterns)
- `backend/events/types.py` — existing event types and `EventBase`
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/shared/types.py` — for reference types

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- Reuse the connection registry and ping/pong pattern established in E5-S07
- `PipelineProgressEvent` extends `EventBase` with fields: `knowledge_base_id: str`, `stage: str`, `progress: float`, `message: str | None`
- Client subscribe message: `{"subscribe": {"kb_id": "..."}}` — only receives events for that KB
- A client that subscribes to kb_id "abc" must NOT receive events for kb_id "xyz"
- JSON message format: `{"type": "pipeline_progress", "event_type": "...", "knowledge_base_id": "...", "progress": 0.5, "timestamp": "..."}`
- Ping/pong keep-alive reuses the same 30s pattern from E5-S07
- Consider extracting a shared `ConnectionManager` class if the alert and pipeline hubs share significant logic

## What NOT To Do
- Do NOT duplicate the connection management infrastructure — refactor shared logic from E5-S07 if needed
- Do NOT implement pipeline execution logic — the WebSocket only forwards events
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT add authentication or authorization
- Do NOT implement pipeline control (start/stop) via WebSocket — that belongs in REST endpoints

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
