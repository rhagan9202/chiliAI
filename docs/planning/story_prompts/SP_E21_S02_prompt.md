# Story E21-S02: AlertingConfig schema extension — dedup window, max alerts, severity levels

## Story
As a platform developer, I want `AlertingConfig` in `config/schema.py` to include `dedup_window_seconds`, `max_alerts_per_entity`, and `severity_levels` so these production alerting parameters are configurable per domain deployment rather than hardcoded.

## Acceptance Criteria
1. `config/schema.py` extends `AlertingConfig` with:
   - `dedup_window_seconds: int = 300` — time window for alert deduplication (5 minutes default)
   - `max_alerts_per_entity: int = 10` — maximum active alerts per entity before suppression
   - `severity_levels: list[str] = ["low", "medium", "high", "critical"]` — ordered list of valid severity tiers for the domain (lowest to highest)
2. All new fields have sensible defaults so existing configs that omit them continue to load without validation errors.
3. `severity_levels` is validated: must be a non-empty list; each element must be a non-empty string.
4. Unit tests cover: default construction, custom severity list, empty severity list raises `ValidationError`, `dedup_window_seconds=0` raises (must be positive).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E8-S02       |

## Target Files
- `backend/config/schema.py` — extend `AlertingConfig` with new fields and validators
- `backend/tests/config/test_schema.py` — add `AlertingConfig` extension tests

## Reference Files to Read First
- `backend/config/schema.py` — current `AlertingConfig` and `DomainConfig`
- `backend/config/defaults/` — default YAML config files (update defaults as needed)
- `backend/tests/config/test_schema.py` — existing config schema tests
- `backend/monitoring/service.py` — how the monitoring service currently uses `AlertingConfig`

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use Pydantic `Field(ge=1)` for `dedup_window_seconds` and `max_alerts_per_entity`
- `severity_levels` must use `Field(min_length=1)` for nonzero list length
- The default `severity_levels` must align with the `SeverityLevel` enum values from E17-S01

## What NOT To Do
- Do not implement the deduplication or suppression logic here — those are E8-S02 and E8-S03
- Do not add escalation policies or suppression rule models here — future story
- Do not change existing `AlertingConfig` fields (`threshold`, `rule`)

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=config tests/config/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
