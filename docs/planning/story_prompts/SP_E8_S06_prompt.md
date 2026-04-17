# Story E8-S06: Alert grouping and correlation

## Story
As a platform developer, I want the monitoring service to group related alerts into alert groups.

## Acceptance Criteria
1. `monitoring/models.py` defines `AlertGroup` with `group_id`, `alert_ids`, `entity_type`, `created_at`, `correlation_reason`.
2. After alert generation, grouping pass clusters alerts sharing entity type within configurable time tolerance (default 300 seconds).
3. `MonitoringEvaluationResponse` gains `alert_groups: list[AlertGroup]`.
4. Tests verify grouping of related alerts and non-grouping of dissimilar.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | E8-S05       |

## Target Files
- `backend/monitoring/models.py` — add `AlertGroup` model with `group_id: str`, `alert_ids: list[str]`, `entity_type: str`, `created_at: datetime`, `correlation_reason: str`
- `backend/monitoring/service.py` — add grouping pass after alert generation in `evaluate()`, cluster alerts by entity type within time tolerance, populate `alert_groups` on response
- `backend/monitoring/service_models.py` — add `alert_groups: list[AlertGroup] = Field(default_factory=list)` to `MonitoringEvaluationResponse`
- `backend/tests/monitoring/test_models.py` — add tests for `AlertGroup` construction
- `backend/tests/monitoring/test_service.py` — add tests for grouping of related alerts and non-grouping of dissimilar alerts

## Reference Files to Read First
- `backend/monitoring/models.py` — existing models (`MonitoringObservation`, `MonitoringBatch`, `AlertCandidate`)
- `backend/monitoring/service.py` — current `MonitoringService.evaluate()` flow including rate limiting, dedup, suppression
- `backend/monitoring/service_models.py` — current `MonitoringEvaluationResponse` with `suppressed_count`, `suppressed_by_rule_count`, `rate_limited_count`
- `backend/shared/types.py` — `Alert` model with `entity_id`, `entity_type`, `created_at` fields
- `backend/shared/utils.py` — `utc_now()` utility and `generate_id()` if available
- `backend/tests/monitoring/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Grouping is a post-processing pass on the generated alerts — do not modify alert generation logic
- Grouping key: alerts with the same `entity_type` whose `created_at` timestamps fall within the configurable time tolerance (default 300 seconds) are grouped together
- `group_id` should be generated using the project's ID generation pattern (e.g., `uuid4().hex` or `shared.utils.generate_id()`)
- `correlation_reason` should be a human-readable string like `"Same entity_type 'provider' within 300s window"`
- Time tolerance should be configurable — add to `AlertsConfig` in `config/schema.py` or accept as a parameter in evaluate
- Alerts that don't match any group remain ungrouped (no singleton groups needed)
- A single alert can belong to at most one group

## What NOT To Do
- Do NOT implement complex correlation algorithms (ML-based, graph-based, etc.) — simple entity-type + time-window clustering is sufficient
- Do NOT add API endpoints for managing alert groups
- Do NOT add alert group lifecycle management (merging, splitting, closing groups)
- Do NOT add cross-knowledge-base grouping — grouping is per-evaluation
- Do NOT modify the alert generation pipeline itself — grouping is a read-only post-processing step
- Do NOT modify files outside `backend/monitoring/`, `backend/config/schema.py`, and `backend/tests/monitoring/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
