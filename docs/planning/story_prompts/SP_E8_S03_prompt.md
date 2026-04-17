# Story E8-S03: Alert suppression rules and maintenance windows

## Story
As a platform operator, I want to define suppression rules preventing alert generation during planned maintenance.

## Acceptance Criteria
1. `monitoring/models.py` defines `SuppressionRule` with `entity_type`, `metric_name`, `start_time`, `end_time`, `reason`.
2. `MonitoringService` accepts `suppression_rules: list[SuppressionRule]` (injectable, default empty).
3. Matching observations excluded from threshold evaluation.
4. `MonitoringEvaluationResponse` gains `suppressed_by_rule_count: int = 0`.
5. Tests verify suppression matching by entity type, metric name, time range.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E8-S02       |

## Target Files
- `backend/monitoring/models.py` — add `SuppressionRule` model with `entity_type: str | None`, `metric_name: str | None`, `start_time: datetime`, `end_time: datetime`, `reason: str`
- `backend/monitoring/service.py` — accept `suppression_rules` parameter (injectable via constructor or `evaluate()` method), filter matching observations before threshold evaluation, track `suppressed_by_rule_count`
- `backend/monitoring/service_models.py` — add `suppressed_by_rule_count: int = 0` to `MonitoringEvaluationResponse`
- `backend/tests/monitoring/test_models.py` — add tests for `SuppressionRule` construction and validation
- `backend/tests/monitoring/test_service.py` — add tests for suppression by entity type, metric name, time range, and combinations

## Reference Files to Read First
- `backend/monitoring/models.py` — existing models (`MonitoringObservation`, `MonitoringBatch`, `AlertCandidate`)
- `backend/monitoring/service.py` — current `MonitoringService` constructor, `evaluate()` method, and dedup logic (from E8-S02)
- `backend/monitoring/service_models.py` — current request/response models including `suppressed_count` (from E8-S02)
- `backend/tests/monitoring/test_service.py` — existing test patterns and fixtures
- `backend/tests/monitoring/test_models.py` — existing model tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `SuppressionRule` uses optional `entity_type` and `metric_name` — `None` means "match all" for that dimension
- Suppression matching: a rule matches an observation if (a) `entity_type` is `None` or matches the observation's entity type, AND (b) `metric_name` is `None` or matches the observation's metric name, AND (c) the current evaluation time is between `start_time` and `end_time`
- Suppression rules are injected into the service at construction time — they are not per-request
- Suppression filtering runs before deduplication and threshold evaluation
- `suppressed_by_rule_count` counts observations excluded by suppression rules, not alerts

## What NOT To Do
- Do NOT add CRUD API endpoints for suppression rules — that is a future API story
- Do NOT persist suppression rules to a database — they are injected at service construction
- Do NOT add alert rate limiting — that is E8-S04
- Do NOT add alert grouping logic — that is E8-S06
- Do NOT add complex matching patterns (regex, glob) for entity_type or metric_name — exact string match or None wildcard is sufficient
- Do NOT modify files outside `backend/monitoring/` and `backend/tests/monitoring/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
