# Story E7-S03: Timeseries — Sliding Window Continuous Analysis

## Story
As a platform developer, I want the timeseries service to support sliding-window analysis over most recent N observations.

## Acceptance Criteria
1. `TimeseriesAnalysisRequest` gains `window_size: int | None = None`.
2. When set, only last `window_size` observations analyzed.
3. Tests verify window truncation and that results differ from full-history.
4. Zero or negative raises `TimeseriesConfigurationError`.

## Priority / Size / Dependencies

| Field        | Value |
|--------------|-------|
| Priority     | P2    |
| Size         | S     |
| Dependencies | None  |

## Target Files
- `backend/analytics/timeseries/service_models.py` — add `window_size: int | None = None` to `TimeseriesAnalysisRequest`
- `backend/analytics/timeseries/service.py` — add window truncation logic before analysis
- `backend/analytics/timeseries/exceptions.py` — add `TimeseriesConfigurationError` if not already present
- `backend/tests/analytics/timeseries/test_service.py` — add tests for window truncation, differing results, and invalid window_size

## Reference Files to Read First
- `backend/analytics/timeseries/service.py` — current service implementation
- `backend/analytics/timeseries/service_models.py` — current request/response models
- `backend/analytics/timeseries/exceptions.py` — existing exception types
- `backend/tests/analytics/timeseries/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Window truncation must happen before any detection strategy is applied (works with all strategies)
- `window_size` of `None` means full history (backward-compatible default)
- Validation of `window_size` should happen early in the request processing, before data loading

## What NOT To Do
- Do NOT change any detection strategy logic — window is a pre-processing step only
- Do NOT add API endpoints — this is service-layer only
- Do NOT import from other analytics sub-modules
- Do NOT silently clamp invalid window sizes — raise `TimeseriesConfigurationError`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=analytics/timeseries tests/analytics/timeseries/` >= 85% coverage
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `TimeseriesAnalysisRequest.window_size: int |
None = None` was added; the service truncates the incoming series to the
most recent `window_size` observations before any detection strategy runs.
Zero or negative window sizes raise `TimeseriesConfigurationError`.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/analytics/timeseries/` exercises
windowed vs. full-history truncation and the validation error path; module
coverage 94%.
