# Story E10-S10: Input validation hardening

## Story
As a platform developer, I want all file-upload and user-input endpoints to enforce strict validation (file size limits, content-type allow list, filename sanitization), so that the platform is protected against injection and abuse.

## Acceptance Criteria
1. File upload endpoint enforces: max size from config (default 50 MB), content-type allow list (`text/plain`, `application/json`, `text/csv`, `application/vnd.openxmlformats-officedocument.*`, `application/pdf`), filename sanitization (strip path traversal, null bytes, control characters).
2. All string inputs to query endpoints are length-bounded (configurable, default 10,000 chars).
3. RAG question input is trimmed and validated for minimum length (1 char) and maximum length (5,000 chars).
4. Tests verify: oversized file → 413, disallowed content type → 415, malicious filename → sanitized, overlength query → 422.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | M    | None         |

## Target Files
- `backend/shared/validation.py` — new validation utilities (filename sanitization, size checks, content-type validation)
- `backend/api/routers/` — update upload and query routers with validation
- `backend/config/schema.py` — add `ValidationConfig` section (max file size, allowed types, max query length)
- `backend/tests/api/test_input_validation.py` — validation endpoint tests
- `backend/tests/shared/test_validation.py` — unit tests for validation utilities

## Reference Files to Read First
- `backend/api/routers/` — existing upload and query endpoint implementations
- `backend/ingestion/validator.py` — existing ingestion validation logic
- `backend/config/schema.py` — existing config schema structure
- `backend/shared/utils.py` — existing shared utilities

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Validation utilities go in `shared/validation.py` — reusable across API and ingestion
- Config-driven limits: all thresholds configurable via `ValidationConfig`, not hardcoded
- Use proper HTTP status codes: 413 (payload too large), 415 (unsupported media type), 422 (unprocessable entity)
- Filename sanitization must handle: `../../etc/passwd`, `foo\x00.txt`, `CON.txt` (Windows reserved), Unicode normalization

## What NOT To Do
- Do NOT trust the `Content-Type` header alone — validate file magic bytes if feasible
- Do NOT allow path traversal in filenames under any circumstances
- Do NOT log full file contents on validation failure — log only metadata (name, size, type)
- Do NOT apply validation only at the API layer — `shared/validation.py` must be usable from ingestion too
- Do NOT use regex-only filename sanitization — use `pathlib` and explicit character stripping
- Do NOT block valid Unicode filenames — only strip control characters and path traversal sequences

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/test_validation.py` >= 85% coverage for validation module
- [ ] `pytest --cov=api tests/api/test_input_validation.py` >= 85% coverage for endpoint validation
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
