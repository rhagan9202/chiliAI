# Story E7-S01: Timeseries — Seasonal Decomposition Anomaly Detection

## Story
As a platform developer, I want the timeseries service to support STL seasonal decomposition alongside z-score detection.

## Acceptance Criteria
1. `TimeseriesService` accepts `detection_strategy: Literal["z_score", "stl_decomposition"]` parameter (configurable via `TimeseriesAnalysisRequest` with default `"z_score"`).
2. New `_detect_anomalies_stl()` decomposes series into trend, seasonal, residual; flags residuals beyond z-threshold.
3. Tests verify seasonal data produces fewer false positives under STL than raw z-score.
4. Existing z-score path unchanged.

## Priority / Size / Dependencies

| Field        | Value |
|--------------|-------|
| Priority     | P2    |
| Size         | M     |
| Dependencies | None  |

## Target Files
- `backend/analytics/timeseries/service_models.py` — add `detection_strategy` field to `TimeseriesAnalysisRequest`
- `backend/analytics/timeseries/service.py` — add `_detect_anomalies_stl()` method and routing logic
- `backend/analytics/timeseries/models.py` — add any new domain types if needed (e.g., decomposition result)
- `backend/tests/analytics/timeseries/test_service.py` — add tests for STL decomposition strategy
- `backend/pyproject.toml` — add `statsmodels` to optional `[analytics]` dependency group

## Reference Files to Read First
- `backend/analytics/timeseries/service.py` — current service implementation with z-score detection
- `backend/analytics/timeseries/service_models.py` — current request/response models
- `backend/analytics/timeseries/models.py` — current domain models
- `backend/analytics/timeseries/protocols.py` — service protocol definition
- `backend/analytics/timeseries/exceptions.py` — existing exception types
- `backend/tests/analytics/timeseries/test_service.py` — existing test patterns
- `backend/pyproject.toml` — current dependency configuration
- `docs/architecture.md` — §5 analytics package responsibilities

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use `statsmodels.tsa.seasonal.seasonal_decompose` for STL decomposition
- `statsmodels` added as optional dependency under `[analytics]` extra — guard import with `try/except ImportError`
- Detection strategy is a `Literal` type, not a free string — enforce at the type level
- Default detection strategy remains `"z_score"` to preserve backward compatibility

## What NOT To Do
- Do NOT remove or modify the existing z-score detection logic
- Do NOT make `statsmodels` a required (non-optional) dependency
- Do NOT change the return type or signature of existing public methods in a breaking way
- Do NOT import from other analytics sub-modules (gnn, risk, explainability)
- Do NOT add API endpoints — this is service-layer only

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/timeseries tests/analytics/timeseries/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
