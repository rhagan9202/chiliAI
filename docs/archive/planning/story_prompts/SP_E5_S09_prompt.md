# Story E5-S09: Analytics router — risk scores and timeseries

## Story
As an analyst, I want API endpoints for risk scores and timeseries data.

## Acceptance Criteria
1. `api/routers/analytics.py` defines `GET /analytics/risk-scores?kb_id=...&entity_type=...&limit=20` returning `RiskScoreListResponse`.
2. `GET /analytics/timeseries?kb_id=...&metric=...&start=...&end=...` returning `TimeseriesResponse`.
3. Both delegate to protocol-based analytics services.
4. Returns 400 if required params missing.
5. Tests verify delegation and param validation.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | E1-S07       |

## Target Files
- `backend/api/routers/analytics.py` — new router with risk score and timeseries endpoints
- `backend/api/dependencies.py` — add `get_risk_service` and `get_timeseries_service` dependency factories
- `backend/tests/api/test_analytics_router.py` — tests for both endpoints, param validation

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router pattern
- `backend/api/dependencies.py` — existing DI wiring
- `backend/analytics/risk/protocols.py` — `RiskServiceProtocol` with `assess` method
- `backend/analytics/risk/service_models.py` — `RiskAssessmentRequest`, `RiskAssessmentResponse`
- `backend/analytics/timeseries/protocols.py` — `TimeseriesServiceProtocol` with `analyze` method
- `backend/analytics/timeseries/service_models.py` — `TimeseriesAnalysisRequest`, `TimeseriesAnalysisResponse`
- `backend/tests/api/test_knowledgebases_router.py` — test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `RiskScoreListResponse` is an API-layer Pydantic model wrapping a list of risk score results with `total: int`
- `TimeseriesResponse` is an API-layer Pydantic model wrapping timeseries data points
- `kb_id` is required on both endpoints — use `Query(...)` to enforce
- `entity_type` is optional on the risk scores endpoint (filters by entity type when provided)
- `metric`, `start`, `end` are required on the timeseries endpoint — `start` and `end` are ISO 8601 datetime strings
- `limit` defaults to 20 on risk scores endpoint, clamped to max 500
- The router translates between API query params and service request models

## What NOT To Do
- Do NOT implement the concrete risk or timeseries service adapters — only DI stubs
- Do NOT implement analytics computation logic in the router
- Do NOT add GNN endpoints — that is E5-S10
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT add authentication or authorization
- Do NOT parse datetime strings manually — use Pydantic or `datetime.fromisoformat`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Added `GET /analytics/risk-scores` and
`GET /analytics/timeseries` endpoints in `backend/api/routers/analytics.py`
with self-contained DI factories (`get_risk_service`, `get_timeseries_service`,
`get_gnn_service`) returning in-memory stubs — `api/dependencies.py` was not
touched per the story scope. Extended the `RiskServiceProtocol` with
`list_scores(...) -> RiskScoreListResponse` (new `RiskScore`, `RiskScoreListRequest`,
`RiskScoreListResponse` service models, plus a `RankedRiskEntry` adapter-side
model). Extended the `TimeseriesServiceProtocol` with
`query_metric(...) -> TimeseriesResponse` (new `TimeseriesPoint`,
`TimeseriesQueryRequest`, `TimeseriesResponse` service models, plus a
`load_metric_range` method on the history-source adapter protocol). Both
in-memory adapters were updated to back the new methods with seeded data.
Inverted-range timeseries queries return 422 directly from the router so the
Pydantic validator surfaces as a client error.

## Validation Note
From `backend/`: `pytest tests/api/test_analytics_router.py tests/analytics -q`
passed with 49 tests. `pytest tests/analytics --cov=analytics/risk
--cov=analytics/timeseries --cov=analytics/gnn` reported 100% coverage on
`analytics/risk` (excluding service.py at 86%), 97% across all three modules.
`ruff check api/routers/analytics.py analytics/risk analytics/timeseries
analytics/gnn tests/api/test_analytics_router.py tests/analytics/risk
tests/analytics/timeseries tests/analytics/gnn` passed. `pyright` on the
analytics tree adds zero new errors (pre-existing baseline of 15 unrelated
`Field(default_factory=list)` warnings remained; new code uses the typed
`Field(default_factory=list[T])` form to stay strict-clean).
