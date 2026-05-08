# Story E5-S02: Alerts router — acknowledge and resolve alerts

## Story
As an analyst, I want to acknowledge and resolve alerts with optional resolution notes.

## Acceptance Criteria
1. `POST /alerts/{alert_id}/acknowledge` sets status to "acknowledged" and returns updated alert.
2. `POST /alerts/{alert_id}/resolve` accepts `ResolutionRequest(notes: str | None, resolved_by: str)`, sets status to "resolved", returns updated alert.
3. Returns 404 if alert ID not found.
4. Returns 409 if alert already resolved.
5. Tests cover happy path, 404, 409.

## Priority / Size / Dependencies
| Priority | Size | Dependencies    |
|----------|------|-----------------|
| P1       | S    | E5-S01, E1-S10  |

## Target Files
- `backend/api/routers/alerts.py` — add `POST /alerts/{alert_id}/acknowledge` and `POST /alerts/{alert_id}/resolve`
- `backend/monitoring/protocols.py` — extend `AlertsServiceProtocol` with `acknowledge_alert` and `resolve_alert` methods
- `backend/tests/api/test_alerts_router.py` — add tests for acknowledge, resolve, 404, 409

## Reference Files to Read First
- `backend/api/routers/alerts.py` — the router created in E5-S01
- `backend/shared/types.py` — `Alert` model with `status`, `resolved_by`, `resolution_notes` fields
- `backend/monitoring/protocols.py` — `AlertsServiceProtocol` from E5-S01
- `backend/api/dependencies.py` — `get_alerts_service` dependency factory from E5-S01
- `backend/tests/api/test_alerts_router.py` — existing alert tests from E5-S01

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `ResolutionRequest` is a Pydantic `BaseModel` defined in the router module (it is an API-layer model, not a domain model)
- The router raises `HTTPException(404)` when the service returns `None` for a missing alert
- The router raises `HTTPException(409)` when attempting to resolve an already-resolved alert — the service should indicate this via return value or exception, not the router checking status directly
- Status transitions are: open → acknowledged → resolved, or open → resolved. The service enforces this.

## What NOT To Do
- Do NOT implement the concrete alerts service — only the protocol methods
- Do NOT add state machine validation logic in the router — that belongs in the service layer
- Do NOT modify `shared/types.py`
- Do NOT add authentication or authorization
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT implement event publishing for alert status changes — that is a service concern

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Extended `AlertsServiceProtocol` with
`acknowledge_alert(alert_id)` and `resolve_alert(alert_id, request)`.
The concrete `AlertsService` enforces transitions in the service layer:
404 surfaces as `AlertNotFoundError`, 409 (already resolved) as
`AlertAlreadyResolvedError`. Both `POST /alerts/{alert_id}/acknowledge`
and `POST /alerts/{alert_id}/resolve` translate those exceptions into
`HTTPException(404)` / `HTTPException(409)` respectively. `ResolutionRequest`
lives in `monitoring/service_models.py` and requires a non-empty
`resolved_by` (Pydantic v2 `min_length=1`); `notes` is optional. Updated
records carry `updated_at`, with `acknowledge_alert` setting
`status="acknowledged"` and `acknowledged=True`, and `resolve_alert`
setting `status="resolved"`, `resolved_by`, and `resolution_notes`.

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
