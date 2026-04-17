# Story E5-S01: Alerts router — list alerts

## Story
As an analyst, I want to list alerts with filtering by severity, entity type, and status.

## Acceptance Criteria
1. `api/routers/alerts.py` defines `GET /alerts` with query params: `severity`, `entity_type`, `status`, `limit` (default 50), `offset` (default 0).
2. Response model: `AlertListResponse(items: list[Alert], total: int)`.
3. Router delegates to an injected alerts service (protocol-based).
4. Returns 200 with empty list when no alerts match.
5. Test verifies filtering and pagination.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E1-S10       |

## Target Files
- `backend/api/routers/alerts.py` — new router with `GET /alerts`
- `backend/api/dependencies.py` — add `get_alerts_service` dependency factory
- `backend/monitoring/protocols.py` — extend or create an `AlertsServiceProtocol` with `list_alerts` method
- `backend/monitoring/service_models.py` — add `AlertListRequest` / `AlertListResponse` if needed at service layer
- `backend/tests/api/test_alerts_router.py` — tests for filtering, pagination, empty results

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router pattern (prefix, tags, Depends)
- `backend/api/routers/config.py` — another existing router for structure reference
- `backend/api/dependencies.py` — existing DI wiring pattern with `@lru_cache` and `Depends`
- `backend/shared/types.py` — `Alert` model with fields: `severity`, `entity_type`, `status`, `entity_id`, etc.
- `backend/monitoring/protocols.py` — existing `MonitoringServiceProtocol`
- `backend/tests/api/test_knowledgebases_router.py` — existing test patterns for API routers

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- The `Alert` model lives in `shared/types.py` — do NOT duplicate or redefine it in the router
- Query params `severity`, `entity_type`, `status` are optional `str | None` filters
- The router must use `Depends()` to inject the alerts service — do NOT instantiate services directly
- The alerts service protocol should define a `list_alerts` method returning items and total count
- Use Pydantic `BaseModel` for the response model, not a raw dict

## What NOT To Do
- Do NOT put alert filtering/matching logic in the router — delegate to service
- Do NOT implement the concrete alerts service adapter — only the protocol and DI stub
- Do NOT modify `shared/types.py` — the `Alert` model already has the needed fields from E1-S10
- Do NOT add authentication or authorization — that is a separate concern
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT create WebSocket endpoints — that is E5-S07

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
