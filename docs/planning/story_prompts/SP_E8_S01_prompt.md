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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
