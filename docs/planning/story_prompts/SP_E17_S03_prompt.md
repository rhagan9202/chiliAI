# Story E17-S03: Shared cross-cutting protocols — HealthCheckable, Lifecycle, Measurable

## Story
As a platform developer, I want `shared/protocols.py` to define `HealthCheckable`, `Lifecycle`, and `Measurable` protocols so adapters and services can implement standard observability and startup/shutdown hooks without tight coupling.

## Acceptance Criteria
1. `shared/protocols.py` adds three `Protocol` classes:
   - `HealthCheckable`: `async def health_check(self) -> HealthStatus` (new dataclass `HealthStatus(status: Literal["ok","degraded","unavailable"], detail: str | None = None)`)
   - `Lifecycle`: `async def start(self) -> None` and `async def stop(self) -> None`
   - `Measurable`: `def get_metrics(self) -> dict[str, float]`
2. `HealthStatus` is defined in `shared/types.py` as a Pydantic model (not just a dataclass) so it is JSON-serializable.
3. All three protocols are exported from `shared/__init__.py`.
4. Unit tests cover: `HealthStatus` construction with all three status values; protocol structural checking (a duck-typed class satisfies each protocol via `isinstance` with `runtime_checkable=True`).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | None         |

## Target Files
- `backend/shared/protocols.py` — add `HealthCheckable`, `Lifecycle`, `Measurable` protocols
- `backend/shared/types.py` — add `HealthStatus` Pydantic model
- `backend/shared/__init__.py` — export new protocols and `HealthStatus`
- `backend/tests/shared/test_protocols.py` — create/update with protocol tests

## Reference Files to Read First
- `backend/shared/protocols.py` — current protocol stubs and `Configurable`
- `backend/shared/types.py` — current shared types
- `backend/shared/__init__.py` — current exports
- `docs/architecture.md` §12 — monitoring and observability requirements

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `@runtime_checkable` on all three protocols to allow `isinstance` checks
- `HealthCheckable.health_check` must be `async` — synchronous health checks are wrapped by callers
- `HealthStatus.status` must use `Literal["ok", "degraded", "unavailable"]` not a bare `str`

## What NOT To Do
- Do not implement health check logic in any adapter here — this story is protocol definitions only
- Do not add `Configurable` changes — it already exists
- Do not make `Lifecycle.start/stop` synchronous — they may need to open connections

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
