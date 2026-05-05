# Story E17-S02: Alert enrichment — owner, tags, and domain_config_version

## Story
As a platform developer, I want `Alert` to carry `owner`, `tags`, and `domain_config_version` fields so alerts can be assigned for triage, organised with custom labels, and pinned to the config version that generated them for reproducibility.

## Acceptance Criteria
1. `shared/types.py` adds to `Alert`:
   - `owner: str | None = None` — user or team assigned to the alert
   - `tags: dict[str, str] = Field(default_factory=dict)` — key-value labels
   - `domain_config_version: str | None = None` — config version string from `DomainConfig.version` at alert creation time
2. Existing `Alert` constructors remain valid (all new fields are optional with defaults).
3. `validate_entity()` is unaffected.
4. Unit tests cover: default construction has `owner=None`, `tags={}`, `domain_config_version=None`; round-trip JSON serialization preserves all three fields.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E17-S01      |

## Target Files
- `backend/shared/types.py` — add `owner`, `tags`, `domain_config_version` to `Alert`
- `backend/tests/shared/test_types.py` — add enrichment field tests

## Reference Files to Read First
- `backend/shared/types.py` — current `Alert` model (post E17-S01)
- `backend/config/schema.py` — `DomainConfig.version` field
- `backend/tests/shared/test_types.py` — existing Alert tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `tags` must use `Field(default_factory=dict)` not `tags: dict[str, str] = {}` (mutable default)
- `domain_config_version` is set by the monitoring service at alert creation; do not populate it here
- All fields must be serializable to JSON without custom serializers

## What NOT To Do
- Do not implement alert assignment workflows — this is a data model change only
- Do not add `acknowledged` field back — it is deprecated in favour of `status`
- Do not add `timeline_events` or `visual_layout` to `EvidencePack` here — that is a separate story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
