# Story E5-S03: Investigation router — entity detail and neighborhood query

## Story
As an analyst, I want to retrieve entity details and explore graph neighborhood around an entity.

## Acceptance Criteria
1. `api/routers/investigation.py` defines `GET /investigation/entities/{entity_id}?kb_id=...` returning entity with properties.
2. `GET /investigation/entities/{entity_id}/neighborhood?kb_id=...&depth=2` returns `SubgraphResult`.
3. `depth` clamped to max 5, values above return 422.
4. Returns 404 if entity not found.
5. Tests cover happy path, missing entity, depth clamping.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E2-S03       |

## Target Files
- `backend/api/routers/investigation.py` — new router with entity detail and neighborhood endpoints
- `backend/api/dependencies.py` — add `get_graph_service` dependency factory
- `backend/graph/protocols.py` — extend `GraphServiceProtocol` with `get_entity` and `query_neighborhood` methods
- `backend/graph/service_models.py` — add `NeighborhoodRequest` / `SubgraphResult` if not already present
- `backend/tests/api/test_investigation_router.py` — tests for happy path, 404, depth validation

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router pattern
- `backend/api/dependencies.py` — DI wiring pattern
- `backend/graph/protocols.py` — existing `GraphServiceProtocol` (currently write-only with `upsert_task`)
- `backend/graph/models.py` — `GraphUpsertResult` for model patterns
- `backend/graph/service_models.py` — existing `GraphBuildTask`, `GraphBuildReceipt`
- `backend/shared/types.py` — `Entity`, `Relationship` models
- `backend/tests/api/test_knowledgebases_router.py` — test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `kb_id` is a required query parameter on both endpoints — return 422 if missing
- `depth` defaults to 2, must be an integer >= 1 and <= 5; values > 5 return 422 (use `Query(default=2, ge=1, le=5)`)
- `SubgraphResult` should contain `entities: list[Entity]`, `relationships: list[Relationship]`, and `center_entity_id: str`
- The router delegates all graph access to `GraphServiceProtocol` — no direct graph DB calls
- Entity detail returns the `Entity` model from `shared/types.py`

## What NOT To Do
- Do NOT implement the concrete graph service adapter — only protocol extensions and DI stub
- Do NOT put graph traversal logic in the router
- Do NOT add search functionality — that is E5-S04
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT modify `shared/types.py`
- Do NOT add authentication or authorization

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `api/routers/investigation.py` exposes
`GET /investigation/entities/{entity_id}` and
`GET /investigation/entities/{entity_id}/neighborhood` and ships its own
self-contained `get_graph_service` factory (delegating to
`api.dependencies.get_graph_service`) so tests override via
`dependency_overrides` without touching `api/dependencies.py` or
`api/app.py`. `depth` is validated through `Query(default=2, ge=1, le=5)` so
out-of-range values yield FastAPI's automatic 422. Missing entities return
404 from both endpoints. `graph/service_models.py` gained
`EntityDetailResponse`, `NeighborhoodRequest`, and `NeighborhoodResponse`
to keep the API response shape strictly typed; the underlying
`SubgraphResult` was reused from `graph/models.py`. The protocol additions
(`get_entity`, `query_neighborhood`) were already present from E2-S03 and
required no further changes.

## Validation Note
From `backend/`:
`.venv/bin/pytest tests/api/test_investigation_router.py tests/graph -q`
passed with 63 passed / 2 skipped. `.venv/bin/ruff check
api/routers/investigation.py graph tests/api/test_investigation_router.py
tests/graph` reported no issues. `.venv/bin/pyright
api/routers/investigation.py graph tests/api/test_investigation_router.py
tests/graph` reported 0 errors. Coverage on
`api/routers/investigation.py` is 100% (router stmts) with overall coverage
across the new router and `graph/service_models.py` at 93%.
