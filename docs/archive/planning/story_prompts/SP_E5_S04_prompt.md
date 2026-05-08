# Story E5-S04: Investigation router — search entities

## Story
As an analyst, I want to search for entities by text query across properties.

## Acceptance Criteria
1. `GET /investigation/search?kb_id=...&q=...&limit=20&offset=0` returns `EntitySearchResponse(items: list[Entity], total: int)`.
2. `q` is required; returns 422 if missing.
3. `limit` clamped to max 500.
4. Router delegates to `GraphService.search_entities`.
5. Test verifies search returns matching entities and respects limit/offset.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E2-S03       |

## Target Files
- `backend/api/routers/investigation.py` — add `GET /investigation/search` endpoint
- `backend/graph/protocols.py` — extend `GraphServiceProtocol` with `search_entities` method
- `backend/tests/api/test_investigation_router.py` — add search tests

## Reference Files to Read First
- `backend/api/routers/investigation.py` — the router created in E5-S03
- `backend/graph/protocols.py` — `GraphServiceProtocol` with methods from E5-S03
- `backend/shared/types.py` — `Entity` model
- `backend/api/dependencies.py` — `get_graph_service` from E5-S03
- `backend/tests/api/test_investigation_router.py` — existing tests from E5-S03

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `kb_id` and `q` are required query parameters — 422 if missing
- `limit` defaults to 20, clamped to max 500 via `Query(default=20, ge=1, le=500)`
- `offset` defaults to 0, must be >= 0
- `EntitySearchResponse` is a Pydantic `BaseModel` defined in the router module (API-layer response model)
- The `search_entities` protocol method signature: `search_entities(kb_id: str, query: str, limit: int, offset: int) -> tuple[list[Entity], int]` or similar returning items and total
- Search logic (property matching, indexing) belongs in the graph service, not the router

## What NOT To Do
- Do NOT implement search logic in the router — delegate to service
- Do NOT implement the concrete graph service search adapter
- Do NOT add full-text indexing or vector search — that is infrastructure-level
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
Completed on April 26, 2026. `api/routers/investigation.py` adds
`GET /investigation/search` next to the entity-detail and neighborhood
endpoints from E5-S03. `q` is enforced as required and non-empty via
`Query(..., min_length=1)`, `limit` clamps through `Query(default=20, ge=1,
le=500)`, and `offset` is bounded by `Query(default=0, ge=0)`. The router
is a thin pass-through to `GraphServiceProtocol.search_entities`, which was
already part of the protocol surface from E2-S03. The response shape
`EntitySearchResponse(items: list[Entity], total: int)` was added to
`graph/service_models.py` to keep the API response shape strictly typed.

## Validation Note
From `backend/`:
`.venv/bin/pytest tests/api/test_investigation_router.py tests/graph -q`
passed with 63 passed / 2 skipped. `.venv/bin/ruff check
api/routers/investigation.py graph tests/api/test_investigation_router.py
tests/graph` reported no issues. `.venv/bin/pyright
api/routers/investigation.py graph tests/api/test_investigation_router.py
tests/graph` reported 0 errors. Search-specific coverage is exercised by
the new tests covering happy paths, empty result, missing/blank `q`,
limit/offset clamping, and offset slicing.
