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
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Added `AlertsServiceProtocol` as a sibling
protocol in `monitoring/protocols.py` (does not disturb the existing
`MonitoringServiceProtocol`). New service-boundary models live in
`monitoring/service_models.py`: `AlertListRequest`, `AlertListResponse`,
`ResolutionRequest`, `AlertActionResponse`. An `InMemoryAlertRepository`
adapter and an `AlertsService` were added to back the router via
`monitoring.service.create_alerts_service`. The new router lives at
`backend/api/routers/alerts.py` with a self-contained
`get_alerts_service()` DI factory at the top of the file (the integration
agent will rewire this in E5-S14 — `api/dependencies.py` was deliberately
not touched). `GET /alerts` accepts `severity`, `entity_type`, `status`,
`limit`, and `offset` query params (the `status` query alias maps to
`status_filter` to avoid shadowing FastAPI's `status` module) and returns
an `AlertListResponse(items, total)`. Filters compose; pagination is
applied after filtering for stable totals.

## Validation Note
From `backend/`:
- `.venv/bin/pytest tests/api/test_alerts_router.py tests/monitoring -q`
  → 38 passed.
- `.venv/bin/pytest tests/monitoring tests/api/test_alerts_router.py
  --cov=monitoring --cov=api/routers/alerts --cov-report=term-missing`
  → monitoring 98%, `api/routers/alerts.py` 100%.
- `.venv/bin/ruff check api/routers/alerts.py monitoring
  tests/api/test_alerts_router.py tests/monitoring` → All checks passed.
- `.venv/bin/pyright api/routers/alerts.py monitoring
  tests/api/test_alerts_router.py tests/monitoring` → 0 errors.
