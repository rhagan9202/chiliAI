# Story E5-S14: Register all new routers in the app factory

## Story
As a platform developer, I want all new routers registered in `api/app.py`.

## Acceptance Criteria
1. `api/app.py` includes all routers: alerts, investigation, chat, ws, analytics, knowledgebases.
2. Each under consistent prefix.
3. `GET /health` still works.
4. Integration test verifies all route prefixes registered.

## Priority / Size / Dependencies
| Priority | Size | Dependencies                                |
|----------|------|---------------------------------------------|
| P1       | XS   | E5-S01, E5-S03, E5-S05, E5-S07, E5-S09, E5-S11 |

## Target Files
- `backend/api/app.py` — register all new routers and remove the TODO comment about missing routers
- `backend/tests/api/test_app.py` — integration test verifying all route prefixes are registered and `/health` works

## Reference Files to Read First
- `backend/api/app.py` — current app factory with `config_router` and `knowledgebases_router` registered, plus TODO listing missing routers
- `backend/api/routers/alerts.py` — alerts router from E5-S01/E5-S02
- `backend/api/routers/investigation.py` — investigation router from E5-S03/E5-S04
- `backend/api/routers/chat.py` — chat router from E5-S05/E5-S06
- `backend/api/routers/ws.py` — WebSocket router from E5-S07/E5-S08
- `backend/api/routers/analytics.py` — analytics router from E5-S09/E5-S10
- `backend/api/routers/knowledgebases.py` — existing KB router (already registered)

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Router prefix conventions (consistent with existing `/config` and `/knowledgebases`):
  - `/alerts` — alerts router
  - `/investigation` — investigation router
  - `/chat` — chat router
  - `/ws` — WebSocket router (alert and pipeline hubs)
  - `/analytics` — analytics router
  - `/knowledgebases` — existing KB router (already registered)
  - `/config` — existing config router (already registered)
- Import pattern: `from api.routers.{module} import router as {module}_router`
- Order: register all REST routers first, then WebSocket router
- Remove the TODO comment block about missing routers after registering them
- `GET /health` must continue to work unchanged
- The integration test should use `TestClient` from `fastapi.testclient` and verify that routes for each prefix return non-404 responses (or at least that the routes are registered)

## What NOT To Do
- Do NOT modify any router implementations — only import and register them
- Do NOT add middleware, authentication, rate limiting, or error handlers — those are separate stories
- Do NOT add API versioning (e.g., `/v1/` prefix) — that is a future concern
- Do NOT remove or modify the existing `config_router` or `knowledgebases_router` registrations
- Do NOT remove the `GET /health` endpoint
- Do NOT change CORS configuration

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
