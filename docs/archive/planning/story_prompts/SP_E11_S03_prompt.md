# Story E11-S03: Config management API endpoints

## Story
As a frontend developer or operator, I want REST endpoints to read the full domain config schema, update the config, force a reload, and query feature flags, so the configuration editor page can render dynamic forms and apply changes.

## Acceptance Criteria
1. `GET /config/domain/schema` returns a JSON Schema object derived from `DomainConfig` via Pydantic's `.model_json_schema()`.
2. `POST /config/domain` accepts a full or partial config payload, validates it against `DomainConfig`, persists it to disk, and triggers `ConfigCache.reload()`. Returns `200` with the merged config or `422` on validation failure.
3. `POST /config/reload` forces `ConfigCache.reload()` and returns `{"status": "reloaded"}`.
4. `GET /config/features` derives a flat feature-flag dict from `DomainConfig` capabilities (enabled adapters, module presences) and returns it.
5. All endpoints require appropriate authentication guard (stub `Depends(require_auth)` — full auth is E10-S06).
6. Unit tests cover schema endpoint, update validation failure, update success + reload, and forced reload.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E11-S01, E11-S02, E5-S14 |

## Target Files
- `backend/api/routers/config.py` — add `schema`, `update`, `reload`, `features` endpoints
- `backend/tests/api/test_config_router.py` — unit tests for all four new endpoints

## Reference Files to Read First
- `backend/api/routers/config.py` — existing `GET /config/domain` endpoint
- `backend/config/loader.py` — `ConfigCache` (post E11-S02) and `load_config()`
- `backend/config/schema.py` — `DomainConfig` Pydantic model
- `backend/api/dependencies.py` — current DI helpers
- `backend/api/app.py` — router registration pattern

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Validate with Pydantic before writing to disk
- Do not expose internal file paths in API responses
- Add `ETag`/`Last-Modified` headers to `GET /config/domain` and `GET /config/domain/schema` for caching
- Auth guard must be a `Depends()` stub — do not hardcode credentials or skip auth entirely

## What NOT To Do
- Do not implement the auth middleware itself — that is E10-S06
- Do not implement CORS or health-check changes here — those are E11-S04 and E11-S05
- Do not allow arbitrary file-system writes — config writes must be restricted to the configured config file path

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
