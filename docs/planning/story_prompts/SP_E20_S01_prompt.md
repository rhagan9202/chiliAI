# Story E20-S01: Timeseries adapter protocol — batch analysis and date-range filtering

## Story
As a platform developer, I want the `TimeseriesAdapterProtocol` to expose batch analysis and date-range filtering so that production adapters can process multiple metrics at once and support historical windowing queries.

## Acceptance Criteria
1. `analytics/timeseries/adapters/protocols.py` adds to `TimeseriesAdapterProtocol`:
   - `batch_analyze(requests: list[TimeseriesAnalysisRequest]) -> list[TimeseriesAnalysisResult]`
   - Filter parameters on `analyze()`: `start_date: datetime | None = None`, `end_date: datetime | None = None` as optional keyword args.
2. `analytics/timeseries/models.py` (or wherever the request model lives) adds `start_date` and `end_date` optional fields to `TimeseriesAnalysisRequest`.
3. The in-memory/baseline adapter implements `batch_analyze` as a loop over `analyze()` calls.
4. Unit tests cover: batch of two requests, date range passed through to request, empty batch returns empty list.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | None         |

## Target Files
- `backend/analytics/timeseries/adapters/protocols.py` — add `batch_analyze` and date range params
- `backend/analytics/timeseries/models.py` — add date range fields to request model
- `backend/analytics/timeseries/adapters/in_memory.py` — implement `batch_analyze`
- `backend/tests/analytics/timeseries/test_adapter.py` — add batch and date-range tests

## Reference Files to Read First
- `backend/analytics/timeseries/adapters/protocols.py` — current protocol
- `backend/analytics/timeseries/models.py` — existing request/result models
- `backend/analytics/timeseries/adapters/in_memory.py` — baseline adapter
- `backend/tests/analytics/timeseries/` — existing tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `start_date`/`end_date` are `datetime` objects (timezone-aware preferred); the adapter is responsible for filtering its input data
- Backward compatibility is mandatory — existing callers that omit date range params must work unchanged
- `batch_analyze` must return results in the same order as the input request list

## What NOT To Do
- Do not implement streaming in this story
- Do not change the timeseries service layer — protocol extension only
- Do not add date-range filtering logic to the service layer; that belongs in the adapter

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/timeseries tests/analytics/timeseries/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
