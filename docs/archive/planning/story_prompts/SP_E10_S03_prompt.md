# Story E10-S03: Backend test coverage gap closure — config module

## Story
As a platform developer, I want ≥ 85% test coverage for the `config/` module, so that configuration loading, validation, and defaults are fully tested.

## Acceptance Criteria
1. `pytest --cov=config tests/config/` reports ≥ 85% line coverage.
2. Tests cover: valid config load, missing file fallback, schema validation errors, cross-field validators (e.g., dimensions mismatch), all config section defaults.
3. Tests cover the domain-specific sections added in E1-S04 through E1-S06.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E1-S06       |

## Target Files
- `backend/tests/config/test_loader.py` — config loading and file-not-found tests
- `backend/tests/config/test_schema.py` — schema validation and default value tests
- `backend/tests/config/conftest.py` — shared fixtures (temp config files, etc.)

## Reference Files to Read First
- `backend/config/loader.py` — config loading logic
- `backend/config/schema.py` — Pydantic schema with validators
- `backend/config/defaults/` — default config files
- `backend/tests/config/` — existing tests to identify gaps

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `tmp_path` fixture for temporary config files — no writing to the source tree
- Test every validator branch in the schema, including cross-field constraints
- Follow existing test patterns in the config test directory

## What NOT To Do
- Do NOT modify production config code to inflate coverage — test what exists
- Do NOT create config files in the source tree during tests — use `tmp_path`
- Do NOT skip domain-specific config sections (E1-S04 through E1-S06 content)
- Do NOT hardcode file paths — always use fixtures or `tmp_path`
- Do NOT weaken validators to make tests pass

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=config tests/config/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
