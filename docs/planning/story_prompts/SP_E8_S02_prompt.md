# Story E8-S02: Alert deduplication within configurable window

## Story
As a platform developer, I want the monitoring service to suppress duplicate alerts for the same entity and metric within a configurable deduplication window.

## Acceptance Criteria
1. `MonitoringService` maintains deduplication index keyed by `(entity_id, metric_name)` with last-alert timestamps.
2. `MonitoringConfig.dedup_window_seconds` (default 3600) controls suppression interval.
3. Duplicate suppressed and counted in `suppressed_count`.
4. `MonitoringEvaluationResponse` gains `suppressed_count: int = 0`.
5. Tests verify deduplication within and outside window.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E1-S06       |

## Target Files
- `backend/config/schema.py` — add `dedup_window_seconds: int = 3600` to `AlertsConfig` (or create `MonitoringConfig` if appropriate)
- `backend/monitoring/service.py` — add deduplication index to `MonitoringService`, filter duplicates during `evaluate()`, track `suppressed_count`
- `backend/monitoring/service_models.py` — add `suppressed_count: int = 0` field to `MonitoringEvaluationResponse`
- `backend/tests/monitoring/test_service.py` — add tests for deduplication within window, outside window, and multiple entity/metric combinations

## Reference Files to Read First
- `backend/monitoring/service.py` — current `MonitoringService` class, constructor, and `evaluate()` method
- `backend/monitoring/service_models.py` — current `MonitoringEvaluationRequest` and `MonitoringEvaluationResponse`
- `backend/monitoring/models.py` — `AlertCandidate` fields (entity_id, metric_name)
- `backend/config/schema.py` — existing `AlertsConfig` and config structure
- `backend/shared/types.py` — `Alert` model with `entity_id` and `metric_name` fields
- `backend/shared/utils.py` — `utc_now()` utility
- `backend/tests/monitoring/test_service.py` — existing test patterns and fixtures

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Deduplication index is in-memory on the `MonitoringService` instance — no external state store
- The dedup key is a tuple of `(entity_id, metric_name)` — both must match for suppression
- Dedup state must survive across multiple `evaluate()` calls on the same service instance
- Config value `dedup_window_seconds` should be read from the service's config, not from the request
- The `suppressed_count` in the response counts alerts that would have been generated but were suppressed by dedup logic in this evaluation call

## What NOT To Do
- Do NOT add persistent storage for deduplication state — in-memory is sufficient
- Do NOT add alert suppression rules or maintenance windows — that is E8-S03
- Do NOT add rate limiting — that is E8-S04
- Do NOT modify the `ObservationSourceProtocol` or adapter layer
- Do NOT add any REST API endpoints for managing dedup state
- Do NOT modify files outside `backend/monitoring/`, `backend/config/schema.py`, and `backend/tests/monitoring/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
