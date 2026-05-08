# Story E11-S01: Config overlay/merging — env-specific overrides and secrets resolution

## Story
As a platform operator, I want the config loader to support a base + environment-specific overlay pattern so production secrets and environment-tuned values can override the base config without modifying it directly.

## Acceptance Criteria
1. `config/loader.py` accepts an optional `overlay_path: str | Path | None` parameter alongside the base config path.
2. When an overlay file is provided it is deep-merged on top of the base config; scalar values are replaced, lists are replaced (not appended), dicts are recursively merged.
3. String values matching the pattern `${ENV_VAR}` are resolved from `os.environ`; unresolvable references raise `ConfigLoadError` with the variable name.
4. `load_config()` is updated and remains backward-compatible (overlay and secret resolution are opt-in via the parameter or a second positional arg).
5. Unit tests cover: overlay-only keys, overlay-overrides-base keys, env-var expansion success, env-var expansion failure, and nested dict merging.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | None         |

## Target Files
- `backend/config/loader.py` — add overlay loading, deep-merge logic, and `${ENV_VAR}` resolution
- `backend/tests/config/test_loader.py` — add unit tests for overlay and secrets resolution

## Reference Files to Read First
- `backend/config/loader.py` — current `load_config()` implementation and `_resolve_path`
- `backend/config/schema.py` — `DomainConfig` schema
- `backend/config/defaults/` — default YAML files to understand the config structure
- `backend/tests/config/` — existing config tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No new third-party dependencies — use `os.environ` and standard dict merging
- The base config file must not be modified or deleted by the overlay logic
- Overlay and resolution happen before Pydantic validation so the final merged dict is validated once
- See `docs/config_engine_plan.md` for the full config engine design

## What NOT To Do
- Do not implement hot-reload here — that is E11-S02
- Do not implement a config management API — that is E11-S03
- Do not append lists from overlay to base lists; overlay always replaces
- Do not add PyYAML merge key (`<<`) support — explicit key merging only

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=config tests/config/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
