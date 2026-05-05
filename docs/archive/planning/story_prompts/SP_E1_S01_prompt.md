# Story E1-S01: Add audit and versioning fields to Entity

## Story
As a platform developer, I want `Entity` to carry `created_at`, `updated_at`, and `version` fields, so that graph merge logic can detect changes and enforce optimistic concurrency control.

## Acceptance Criteria
1. `Entity` in `shared/types.py` has `created_at: datetime`, `updated_at: datetime | None = None`, and `version: int = 1`.
2. `created_at` defaults to UTC now via the shared `utc_now()` utility (see E1-S03).
3. Existing tests that construct `Entity` instances still pass (fields have defaults).
4. `validate_entity()` does not validate audit fields against `PropertyDefinition` — they are platform-owned, not domain-owned.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | E1-S03       |

## Target Files
- `backend/shared/types.py` — add `created_at`, `updated_at`, `version` fields to `Entity`
- `backend/tests/shared/test_types.py` — add/update tests for the new fields

## Reference Files to Read First
- `backend/shared/types.py` — current `Entity` model, `validate_entity()` function, and all existing types
- `backend/shared/utils.py` — where `utc_now()` will live after E1-S03 (dependency)
- `backend/tests/shared/test_types.py` — existing test patterns for Entity construction and validation

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `created_at` must use `Field(default_factory=utc_now)` importing from `shared.utils`
- Audit fields (`created_at`, `updated_at`, `version`) are platform-owned — `validate_entity()` must explicitly skip them when comparing actual properties against `PropertyDefinition` keys
- Use `from __future__ import annotations` (already present in the file)
- These fields are consumed by graph upsert idempotency (E2-S05), alert lifecycle, and future RBAC audit logs

## What NOT To Do
- Do NOT modify any files outside `backend/shared/types.py` and `backend/tests/shared/test_types.py`
- Do NOT change `validate_entity()` to validate audit fields — they must be excluded from domain property validation
- Do NOT add domain-specific logic or hardcoded entity types
- Do NOT modify `EntityDefinition` or `RelationshipDefinition`
- Do NOT implement graph merge logic — that belongs to E2-S05
- Do NOT remove or rename any existing fields on `Entity`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=shared tests/shared/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
