# Story E10-S08: Structured logging with structlog

## Story
As a platform operator, I want all backend services to produce structured JSON logs with consistent fields (timestamp, level, correlation_id, module, message), so that logs are queryable in centralized logging systems.

## Acceptance Criteria
1. `structlog` is installed and configured in `api/app.py` and `agent/coordinator.py`.
2. All existing `logging.getLogger()` calls are replaced with `structlog.get_logger()`.
3. Every log entry includes: `timestamp`, `level`, `module`, `correlation_id` (from request or event context), `knowledge_base_id` (when available).
4. JSON output format in production, human-readable format in development (controlled by env var `LOG_FORMAT=json|console`).
5. A test verifies log output structure in JSON mode.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | None         |

## Target Files
- `backend/shared/logging.py` — new structlog configuration module
- `backend/api/app.py` — integrate structlog setup at app startup
- `backend/agent/coordinator.py` — integrate structlog setup at worker startup
- `backend/tests/shared/test_logging.py` — logging configuration and output tests

## Reference Files to Read First
- `backend/api/app.py` — current app factory and startup hooks
- `backend/agent/coordinator.py` — current worker entry point
- `backend/pyproject.toml` — current dependencies (check if structlog is already listed)
- All modules that use `logging.getLogger()` — search for existing usage

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `structlog` must be configured once in `shared/logging.py` and called from both API and worker entry points
- `correlation_id` must be bound from FastAPI request middleware (API) or event metadata (worker)
- No global mutable state — use structlog's context variables or thread-local binding
- The `LOG_FORMAT` env var controls output: `json` (default in production) or `console` (for development)

## What NOT To Do
- Do NOT use `print()` statements for logging
- Do NOT log sensitive data: passwords, API keys, PII, full JWT tokens
- Do NOT create a custom logging framework — use structlog with its standard processors
- Do NOT break existing log sites by changing function signatures — structlog is a drop-in for `logging`
- Do NOT add structlog to every module's imports in this story — replace `logging.getLogger()` calls as you find them, but focus on the entry points and shared config
- Do NOT log request/response bodies by default — only at DEBUG level

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/test_logging.py` >= 85% coverage for logging module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
- [ ] `structlog` added to `pyproject.toml` dependencies
