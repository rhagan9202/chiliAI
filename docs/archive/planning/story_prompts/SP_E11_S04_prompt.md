# Story E11-S04: CORS origins from config or ALLOWED_ORIGINS env var

## Story
As a platform operator, I want the API's CORS allowed-origins list to be driven by the `ALLOWED_ORIGINS` environment variable or the domain config, so it can be set correctly in production without code changes.

## Acceptance Criteria
1. `api/app.py` reads allowed origins from `os.environ.get("ALLOWED_ORIGINS", "")`, split on `,`, stripped of whitespace; falls back to `["http://localhost:5173", "http://localhost:80", "http://localhost"]` when the env var is absent or empty.
2. The hardcoded comment `# TODO(production)` is removed.
3. Unit tests verify: env var present with multiple origins, env var absent (uses defaults), empty env var string (uses defaults).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/api/app.py` — replace hardcoded origins with env-var-driven logic
- `backend/tests/api/test_app.py` — add CORS origin resolution tests

## Reference Files to Read First
- `backend/api/app.py` — current CORS middleware setup
- `backend/tests/api/` — existing API test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `os.environ` access must be done inside the `create_app()` factory, not at module import time, so tests can monkeypatch the env
- No new dependencies

## What NOT To Do
- Do not read origins from the `DomainConfig` YAML — env var is the right surface for deployment-time secrets/origins
- Do not change any other part of the CORS middleware configuration
- Do not remove the dev defaults — they must remain as the fallback

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
