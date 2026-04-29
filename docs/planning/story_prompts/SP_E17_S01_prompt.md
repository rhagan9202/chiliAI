# Story E17-S01: SeverityLevel enum to replace bare str on Alert

## Story
As a platform developer, I want `Alert.severity` to use a `SeverityLevel` enum (`"low"`, `"medium"`, `"high"`, `"critical"`) instead of a bare `str` so that invalid severity values are rejected at system boundaries and not silently accepted.

## Acceptance Criteria
1. `shared/types.py` adds a `SeverityLevel` string enum: `LOW = "low"`, `MEDIUM = "medium"`, `HIGH = "high"`, `CRITICAL = "critical"`.
2. `Alert.severity` type changes from `str` to `SeverityLevel`.
3. All existing code that constructs `Alert` with a string literal severity must be updated to use the enum.
4. `validate_entity()` is unaffected (severity lives on `Alert`, not `Entity`).
5. Unit tests cover: valid severity values accepted, invalid severity raises `ValidationError`.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | None         |

## Target Files
- `backend/shared/types.py` — add `SeverityLevel` enum, update `Alert.severity`
- `backend/tests/shared/test_types.py` — add severity validation tests
- Any other backend files constructing `Alert` with a string literal severity

## Reference Files to Read First
- `backend/shared/types.py` — current `Alert` model
- `backend/tests/shared/test_types.py` — existing test patterns
- `backend/monitoring/` — monitoring module constructs `Alert` objects

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `enum.StrEnum` (Python 3.11+) so `SeverityLevel.HIGH == "high"` is `True` — preserves JSON serialization compatibility
- Existing serialized JSON with lowercase string values must deserialize correctly — `StrEnum` ensures this
- Do not add domain-specific severity tiers beyond the four standard levels

## What NOT To Do
- Do not add `severity_levels` to `DomainConfig` here — that is a future `AlertingConfig` extension
- Do not change the `Alert.status` field; only `severity` changes in this story
- Do not update frontend TypeScript types — that is a follow-on story (E9 series)

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
