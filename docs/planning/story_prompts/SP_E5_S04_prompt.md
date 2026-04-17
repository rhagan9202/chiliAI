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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
