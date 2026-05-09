# Story E4-S07: Worker health check endpoint

## Story
As a platform operator, I want the worker process to expose a lightweight health check on a configurable HTTP port.

## Acceptance Criteria
1. The worker starts a minimal HTTP server (e.g., `aiohttp` or stdlib `http.server`) on port 8001 (configurable).
2. `GET /health` returns `{"status": "ok", "last_event_processed_at": "<ISO timestamp>"}`.
3. If no event has been processed in 5 minutes, status becomes `"degraded"`.
4. The health server runs in a background asyncio task and does not interfere with event processing.
5. Test verifies the health endpoint responds correctly.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P2          |
| Size         | S           |
| Dependencies | None        |

## Target Files
- `backend/agent/coordinator.py` — integrate health server startup as a background asyncio task, track `last_event_processed_at`
- `backend/agent/health.py` — (new) minimal async HTTP health check server
- `backend/tests/agent/test_health.py` — (new) tests for health endpoint responses

## Reference Files to Read First
- `backend/agent/coordinator.py` — current coordinator structure and asyncio loop
- `backend/agent/models.py` — existing models (for health config placement)
- `backend/config/schema.py` — `DomainConfig` for health port configuration
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use only stdlib or already-declared dependencies — prefer `aiohttp.web` if `aiohttp` is already a dependency, otherwise use `asyncio` + stdlib `http.server` or a lightweight approach
- The health server must run as a background `asyncio.Task` and must not block the event processing loop
- The health port must be configurable (default 8001)
- The 5-minute degraded threshold should be a configurable constant, not a magic number
- Response must be valid JSON with `Content-Type: application/json`

## What NOT To Do
- Do not use FastAPI or add heavy web framework dependencies for a single health endpoint
- Do not block the event loop with synchronous HTTP serving
- Do not expose any sensitive information (internal state, config secrets) via the health endpoint
- Do not make the health server a hard requirement — the worker should still function if the health server fails to start (log a warning)
- Do not add metrics, Prometheus endpoints, or additional routes beyond `/health`

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. New `agent/health.py` exposes `HealthState`
(tracks `last_event_processed_at`, with `mark_event_processed` and a
`status()` that returns `"degraded"` once
`HealthSettings.degraded_after_seconds` (default 300s) is exceeded),
`build_health_payload` (returns `{"status": ..., "last_event_processed_at":
...}`), and `start_health_server` (a stdlib-only `asyncio.start_server`
HTTP responder that hand-parses request lines, returns 200 JSON for `GET
/health`, 404 for unknown paths, and 405 for non-GET). The coordinator
constructs a `HealthState`, calls `start_health_server_safely` on startup
(logging a WARNING and continuing if `OSError` fires), passes the state
into `drain_ingestion_events` so each successful event marks the
timestamp, and closes the server on shutdown. `HealthSettings` lives in
`agent/models.py`. Tests in `tests/agent/test_health.py` exercise the
stdlib server end-to-end (200 + JSON, 404, 405) and the degraded
transition.

## Validation Note
From `backend/`: `pytest tests/agent tests/events tests/api --cov=agent
--cov=events --cov=api --cov-report=term-missing` passed with 91 tests;
agent coverage 87% (`agent/health.py` 90%). `ruff check agent events api
tests/agent tests/events tests/api` passed. `pyright agent events api
tests/agent tests/events tests/api` reported 0 errors.
