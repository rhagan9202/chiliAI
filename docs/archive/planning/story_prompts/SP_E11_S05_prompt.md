# Story E11-S05: API health check — subsystem liveness + Kubernetes readiness endpoint

## Story
As a platform operator, I want `GET /health` to probe real subsystem connectivity (event bus, graph DB, vector store, object store) and report degraded status for each failing subsystem, and I want a `GET /readiness` endpoint suitable for Kubernetes readiness probes.

## Acceptance Criteria
1. `GET /health` calls `health_check()` on each registered subsystem adapter and returns a JSON payload:
   ```json
   {"status": "ok" | "degraded", "subsystems": {"event_bus": "ok", "graph": "degraded: <msg>", ...}}
   ```
2. If all subsystems are healthy, HTTP 200 with `status: ok`. If any subsystem fails, HTTP 200 with `status: degraded` (not 500, to avoid load-balancer drops).
3. `GET /readiness` returns HTTP 200 only when all subsystems report healthy; returns HTTP 503 otherwise. Used by Kubernetes `readinessProbe`.
4. Each adapter that requires health-checking implements the `HealthCheckable` protocol from `shared/protocols.py` (see E17-S03 dependency). For adapters that don't implement it yet, the health check is skipped and the result is `"skipped"`.
5. Unit tests mock all subsystem adapters and cover: all healthy, one degraded, all degraded, skipped (adapter not HealthCheckable).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E17-S03      |

## Target Files
- `backend/api/app.py` — replace stub health route with real probe logic and add readiness route
- `backend/api/dependencies.py` — expose health-checkable adapters via DI
- `backend/tests/api/test_app.py` — health and readiness probe tests

## Reference Files to Read First
- `backend/api/app.py` — current health route stub
- `backend/api/dependencies.py` — DI helpers
- `backend/shared/protocols.py` — `HealthCheckable` protocol (post E17-S03)
- `docs/architecture.md` §12 — monitoring and observability

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Health probes must be non-blocking: use `asyncio.gather` with per-probe timeouts (default 2 s), mark as degraded on timeout
- Do not raise exceptions from the health endpoint — catch and report all errors as degraded
- `/readiness` is separate from `/health` and may return 503

## What NOT To Do
- Do not merge readiness and liveness into a single endpoint
- Do not hardcode subsystem names — derive them from the registered adapters
- Do not fail the build if adapters are not yet HealthCheckable — graceful skip is required

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
