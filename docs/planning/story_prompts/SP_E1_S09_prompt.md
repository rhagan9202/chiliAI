# Story E1-S09: Add updated_at and status enrichment to KnowledgeBase

## Story
As a platform developer, I want `KnowledgeBase` to carry `updated_at` and richer status lifecycle fields.

## Acceptance Criteria
1. `KnowledgeBase` in `shared/types.py` has `updated_at: datetime | None = None`.
2. `status` field type is narrowed to `Literal["active", "building", "ready", "error", "archived"]` with default `"active"`.
3. Existing tests pass.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | XS   | None         |

## Target Files
- `backend/shared/types.py` — add `updated_at` field and narrow `status` type on `KnowledgeBase`
- `backend/tests/shared/test_types.py` — add/update tests for new `KnowledgeBase` fields and status validation

## Reference Files to Read First
- `backend/shared/types.py` — current `KnowledgeBase` model, its fields, and existing TODO comments
- `backend/tests/shared/test_types.py` — existing test patterns for `KnowledgeBase` construction
- `backend/events/types.py` — `KnowledgeBaseCreatedEvent` to understand how KB status flows through events

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The `status` field must use `Literal["active", "building", "ready", "error", "archived"]` — this is a type narrowing from the current bare `str` type
- `updated_at` is `datetime | None = None` — not auto-populated, must be set explicitly by service logic
- Remove the TODO comment in `KnowledgeBase` about `updated_at` since it will be implemented
- Existing tests constructing `KnowledgeBase` with `status="active"` (or no status) must still work

## What NOT To Do
- Do NOT add domain-specific knowledge base types or hardcoded categories
- Do NOT implement KB lifecycle state machine logic — that belongs to a service layer
- Do NOT modify `KnowledgeBaseCreatedEvent` or other event types
- Do NOT add `owner`, `tags`, or `domain_config_version` fields — those are future work noted in TODOs
- Do NOT modify any files outside `backend/shared/types.py` and `backend/tests/shared/test_types.py`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=shared tests/shared/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
