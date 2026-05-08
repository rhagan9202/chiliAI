# Story E1-S02: Add audit and versioning fields to Relationship

## Story
As a platform developer, I want `Relationship` to carry `created_at`, `updated_at`, `version`, and an optional `weight` field, so that relationship upserts support concurrency control and weighted graph algorithms.

## Acceptance Criteria
1. `Relationship` in `shared/types.py` has `created_at: datetime`, `updated_at: datetime | None = None`, `version: int = 1`, and `weight: float | None = None`.
2. `created_at` defaults to UTC now via the shared utility.
3. All existing tests that construct `Relationship` instances still pass.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | E1-S03       |

## Target Files
- `backend/shared/types.py` — add `created_at`, `updated_at`, `version`, `weight` fields to `Relationship`
- `backend/tests/shared/test_types.py` — add/update tests for the new Relationship fields

## Reference Files to Read First
- `backend/shared/types.py` — current `Relationship` model and all existing types
- `backend/shared/utils.py` — where `utc_now()` lives after E1-S03 (dependency)
- `backend/tests/shared/test_types.py` — existing test patterns for Relationship construction

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `created_at` must use `Field(default_factory=utc_now)` importing from `shared.utils`
- `weight` enables PageRank and betweenness centrality in the analytics module — keep it as `float | None = None`
- Use `from __future__ import annotations` (already present in the file)

## What NOT To Do
- Do NOT modify any files outside `backend/shared/types.py` and `backend/tests/shared/test_types.py`
- Do NOT add graph algorithm logic — that belongs to the analytics module
- Do NOT modify `RelationshipDefinition` — that is a config-definition type
- Do NOT remove or rename any existing fields on `Relationship`
- Do NOT add domain-specific relationship types or hardcoded constants

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=shared tests/shared/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
