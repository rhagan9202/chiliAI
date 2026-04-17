# Story E8-S04: Alert rate limiting

## Story
As a platform developer, I want the monitoring service to enforce a maximum alert rate per knowledge base.

## Acceptance Criteria
1. `MonitoringConfig` gains `max_alerts_per_evaluation: int = 100`.
2. When threshold reached, remaining logged as `rate_limited_count` but not surfaced.
3. Highest-severity candidates prioritized.
4. `MonitoringEvaluationResponse` gains `rate_limited_count: int = 0`.
5. Tests verify rate limiting exceeding limit.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | E1-S06       |

## Target Files
- `backend/config/schema.py` — add `max_alerts_per_evaluation: int = 100` to `AlertsConfig` (or `MonitoringConfig` if it exists)
- `backend/monitoring/service.py` — after threshold evaluation and dedup, sort alert candidates by severity descending, cap at `max_alerts_per_evaluation`, and track `rate_limited_count`
- `backend/monitoring/service_models.py` — add `rate_limited_count: int = 0` to `MonitoringEvaluationResponse`
- `backend/tests/monitoring/test_service.py` — add tests for rate limiting: under limit, at limit, over limit with severity prioritization

## Reference Files to Read First
- `backend/monitoring/service.py` — current `MonitoringService.evaluate()` flow, alert generation pipeline
- `backend/monitoring/service_models.py` — current `MonitoringEvaluationResponse` fields
- `backend/monitoring/models.py` — `AlertCandidate` fields, especially severity-related fields
- `backend/config/schema.py` — existing `AlertsConfig` and config loading patterns
- `backend/shared/types.py` — `Alert` model, severity field type
- `backend/tests/monitoring/test_service.py` — existing test patterns and fixtures

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Severity ordering for prioritization: use the existing severity field on `AlertCandidate` or `Alert` — sort by severity descending so highest-severity alerts survive the cap
- Rate limiting applies per `evaluate()` call (per knowledge base per evaluation), not globally across calls
- `rate_limited_count` reflects the number of alert candidates that exceeded the cap and were dropped
- Rate limiting runs after suppression rules (E8-S03) and deduplication (E8-S02) — it is the final stage before response construction
- Log rate-limited alerts at WARNING level using standard logging

## What NOT To Do
- Do NOT implement per-time-period rate limiting (e.g., "max 100 per hour") — only per-evaluation cap
- Do NOT add alert lifecycle state machine — that is E8-S05
- Do NOT add alert grouping — that is E8-S06
- Do NOT add external rate-limiting infrastructure (Redis, token buckets, etc.)
- Do NOT drop or modify existing alert candidates — just exclude extras from the response
- Do NOT modify files outside `backend/monitoring/`, `backend/config/schema.py`, and `backend/tests/monitoring/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
