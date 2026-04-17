# Story E8-S08: Monitoring module test suite — achieve >= 85% coverage

## Story
As a platform developer, I want comprehensive pytest coverage for the monitoring module.

## Acceptance Criteria
1. `pytest --cov=monitoring tests/monitoring/` reports >= 85% line coverage.
2. Tests cover: happy-path evaluation, time-window filtering, deduplication, suppression rules, rate limiting, alert lifecycle transitions, alert grouping, stream consumer error paths.
3. Existing tests expanded — not replaced.

## Priority / Size / Dependencies
| Priority | Size | Dependencies                         |
|----------|------|--------------------------------------|
| P1       | M    | E8-S01, E8-S02, E8-S03, E8-S04, E8-S05, E8-S06 |

## Target Files
- `backend/tests/monitoring/test_service.py` — expand with missing coverage for evaluate flow, edge cases, error paths
- `backend/tests/monitoring/test_models.py` — expand with coverage for `SuppressionRule`, `AlertGroup`, model validation edge cases
- `backend/tests/monitoring/test_in_memory_adapter.py` — expand if adapter has uncovered paths
- `backend/tests/monitoring/test_exceptions.py` — add tests for `AlertLifecycleError` and exception hierarchy if not covered

## Reference Files to Read First
- `backend/monitoring/service.py` — full service implementation including evaluate, dedup, suppression, rate limiting, grouping, `transition_alert_status`
- `backend/monitoring/models.py` — all model classes: `MonitoringObservation`, `MonitoringBatch`, `AlertCandidate`, `SuppressionRule`, `AlertGroup`
- `backend/monitoring/service_models.py` — `MonitoringEvaluationRequest`, `MonitoringEvaluationResponse` with all fields
- `backend/monitoring/exceptions.py` — `MonitoringError`, `MonitoringConfigurationError`, `MonitoringSourceError`, `AlertLifecycleError`
- `backend/monitoring/protocols.py` — `ObservationSourceProtocol` interface
- `backend/monitoring/adapters/in_memory.py` — in-memory adapter implementation
- `backend/tests/monitoring/test_service.py` — existing tests to expand (not replace)
- `backend/tests/monitoring/test_models.py` — existing model tests
- `backend/tests/monitoring/test_in_memory_adapter.py` — existing adapter tests
- `backend/shared/types.py` — `Alert` model
- `backend/config/schema.py` — config schema for monitoring-related settings

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- **Expand existing test files — do NOT delete or replace existing tests**
- Run `pytest --cov=monitoring tests/monitoring/ --cov-report=term-missing` first to identify uncovered lines
- Focus coverage on:
  - Happy-path evaluation (observations → alerts)
  - Time-window filtering edge cases (boundary timestamps, empty windows)
  - Deduplication within and outside window, multiple keys
  - Suppression rule matching (exact match, wildcard None, time boundaries)
  - Rate limiting at, under, and over limit with severity ordering
  - Alert lifecycle: all valid transitions, invalid transitions raising `AlertLifecycleError`
  - Alert grouping: same entity type within tolerance, different types, time boundary
  - Error paths: adapter failures, empty observation lists, invalid configs
- Use `pytest.mark.parametrize` where appropriate for transition and edge-case matrices
- Use `freezegun` or `unittest.mock.patch` for time-dependent tests if already in use

## What NOT To Do
- Do NOT delete or replace existing tests — only add new tests
- Do NOT modify production code in `backend/monitoring/` — this is a test-only story
- Do NOT add integration tests that require external services
- Do NOT add tests for the coordinator handler (E8-S07) — that belongs to agent tests
- Do NOT reduce coverage by removing or skipping existing tests
- Do NOT add new test dependencies unless already present in `pyproject.toml`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
