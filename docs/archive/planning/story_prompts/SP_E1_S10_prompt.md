# Story E1-S10: Add structured fields to EvidencePack and Alert

## Story
As a platform developer, I want `EvidencePack` to carry `created_at` and `source_documents`, and `Alert` to carry `updated_at`, `resolved_by`, and `resolution_notes`.

## Acceptance Criteria
1. `EvidencePack` has `created_at: datetime` and `source_documents: list[str] = Field(default_factory=list)`.
2. `Alert` has `updated_at: datetime | None = None`, `resolved_by: str | None = None`, `resolution_notes: str | None = None`, and `status: Literal["open", "acknowledged", "investigating", "resolved", "dismissed"] = "open"`.
3. All existing tests pass.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | E1-S03       |

## Target Files
- `backend/shared/types.py` — add fields to `EvidencePack` and `Alert`
- `backend/tests/shared/test_types.py` — add/update tests for new `EvidencePack` and `Alert` fields

## Reference Files to Read First
- `backend/shared/types.py` — current `EvidencePack` and `Alert` models, existing fields and TODO comments
- `backend/shared/utils.py` — `utc_now()` utility (from E1-S03) for `EvidencePack.created_at` default
- `backend/tests/shared/test_types.py` — existing test patterns for Alert and EvidencePack construction

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `EvidencePack.created_at` must use `Field(default_factory=utc_now)` importing from `shared.utils`
- `Alert.status` uses `Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]` — this narrows the current implicit status from the `acknowledged: bool` field
- Consider whether `acknowledged: bool` should be kept for backward compatibility or removed in favor of `status` — prefer keeping it for now and marking as deprecated via a comment, unless existing tests don't reference it
- `Alert.updated_at` is `datetime | None = None` — set explicitly by service logic, not auto-populated
- `source_documents` on `EvidencePack` is a list of document IDs linking back to originating source documents
- Remove the TODO comments on `EvidencePack` and `Alert` that are addressed by this story

## What NOT To Do
- Do NOT implement alert lifecycle state machine logic — that belongs to a service layer
- Do NOT add `timeline_events`, `visual_layout`, or other future EvidencePack fields mentioned in TODOs — those are separate work
- Do NOT modify alert-related API routes or event types
- Do NOT add severity enum types — that is mentioned in a TODO but is out of scope for this story
- Do NOT modify any files outside `backend/shared/types.py` and `backend/tests/shared/test_types.py`
- Do NOT remove the existing `acknowledged: bool` field on Alert — maintain backward compatibility

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=shared tests/shared/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
