# Story E8-S01: Time-window aggregation for monitoring evaluation

## Story
As a platform developer, I want the monitoring service to evaluate observations within configurable time windows.

## Acceptance Criteria
1. `MonitoringEvaluationRequest` gains `window_minutes: int = 60` and `min_observations_in_window: int = 1`.
2. Evaluation logic filters observations to those within the time window before applying thresholds.
3. Alert generated only if `min_observations_in_window` observations exceed threshold within window.
4. Tests verify windowed filtering with observations at various timestamps.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/monitoring/service_models.py` — add `window_minutes` and `min_observations_in_window` fields to `MonitoringEvaluationRequest`
- `backend/monitoring/service.py` — update `MonitoringService.evaluate()` to filter observations by time window and enforce `min_observations_in_window` before alerting
- `backend/tests/monitoring/test_service.py` — add tests for windowed filtering with various timestamp scenarios

## Reference Files to Read First
- `backend/monitoring/service_models.py` — current `MonitoringEvaluationRequest` and `MonitoringEvaluationResponse` definitions
- `backend/monitoring/service.py` — current `MonitoringService.evaluate()` implementation and helper functions
- `backend/monitoring/models.py` — `MonitoringObservation` (has `timestamp` or `observed_at` field), `AlertCandidate`, `MonitoringBatch`
- `backend/monitoring/protocols.py` — `ObservationSourceProtocol` interface
- `backend/monitoring/adapters/in_memory.py` — in-memory adapter used in tests
- `backend/tests/monitoring/test_service.py` — existing test patterns and fixtures
- `backend/shared/utils.py` — `utc_now()` utility for time calculations

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Time-window filtering must happen inside `evaluate()` before threshold comparison — do not push filtering into the adapter/protocol layer
- Use `shared.utils.utc_now()` as the reference "now" for window calculations
- Window filtering compares `observation.observed_at` (or equivalent timestamp field) against `now - timedelta(minutes=window_minutes)`
- Default `window_minutes=60` and `min_observations_in_window=1` preserves backward-compatible behavior (all existing tests must still pass)

## What NOT To Do
- Do NOT modify `ObservationSourceProtocol` or adapter interfaces — filtering is a service-layer concern
- Do NOT add sliding-window or rolling-window abstractions — simple cutoff filtering is sufficient
- Do NOT add alert deduplication logic — that is E8-S02
- Do NOT modify `MonitoringEvaluationResponse` in this story
- Do NOT add any new dependencies or packages
- Do NOT modify files outside `backend/monitoring/` and `backend/tests/monitoring/`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Added `window_minutes: int = 60` and `min_observations_in_window: int = 1` to `MonitoringEvaluationRequest`. `MonitoringService.evaluate()` now calls `utc_now()` once per evaluation, computes `now - timedelta(minutes=window_minutes)` as the window start, filters out observations whose `observed_at` is before that cutoff, then groups in-window observations by `(entity_id, metric_name)` and only emits an `AlertCandidate` for groups whose count of threshold-exceeding observations meets `min_observations_in_window`. Threshold comparisons run on the highest-scoring observation in each surviving group, preserving severity classification semantics.

## Validation Note
`pytest tests/monitoring/test_service.py` covers windowed filtering with multiple timestamp scenarios (inside vs outside window, min count not met, min count satisfied across two observations). Backend full suite: 808 passed / 3 skipped, monitoring coverage 99%.
