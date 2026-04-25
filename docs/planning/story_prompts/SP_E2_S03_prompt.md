# Story E2-S03: Extend GraphServiceProtocol and GraphService with query methods

## Story
As a platform developer, I want the graph service to expose `get_entity`, `query_neighborhood`, `search_entities`, and `compute_metrics` through the service protocol.

> Note: `get_subgraph` is intentionally deferred from E2-S03. Although it was mentioned in earlier planning text, it is not part of the acceptance criteria for this story because `GraphRepository` does not yet expose a filtered-subgraph query surface, and that protocol must not be modified here.

## Acceptance Criteria
1. `graph/protocols.py:GraphServiceProtocol` adds: `get_entity(kb_id, entity_id) -> Entity | None`, `query_neighborhood(kb_id, entity_id, depth) -> SubgraphResult`, `search_entities(kb_id, query, limit, offset) -> list[Entity]`, `compute_metrics(kb_id) -> GraphMetrics`.
2. `graph/service.py:GraphService` implements all new methods by delegating to `GraphRepository`.
3. `graph/service_models.py` defines request/response models: `NeighborhoodQuery`, `EntitySearchQuery`, `GraphMetricsResult`.
4. Unit tests verify each service method delegates correctly.

## Priority / Size / Dependencies
- **Priority:** P0
- **Size:** M
- **Dependencies:** E2-S01, E2-S02

## Target Files
- `backend/graph/protocols.py` — add query method signatures to `GraphServiceProtocol`
- `backend/graph/service.py` — implement new methods on `GraphService`
- `backend/graph/service_models.py` — add `NeighborhoodQuery`, `EntitySearchQuery`, `GraphMetricsResult`
- `backend/tests/graph/test_service.py` — add tests for each new service method

## Reference Files to Read First
- `backend/graph/protocols.py` — current `GraphServiceProtocol`
- `backend/graph/service.py` — current `GraphService` implementation
- `backend/graph/service_models.py` — existing request/response models
- `backend/graph/adapters/protocols.py` — `GraphRepository` protocol (after E2-S01)
- `backend/graph/models.py` — `SubgraphResult`, `GraphMetrics` (after E2-S01)
- `backend/shared/types.py` — `Entity`, `Relationship`
- `backend/tests/graph/test_service.py` — existing service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Service methods must validate `depth` (max 5) and `limit` (max 500) to prevent runaway queries — raise `ValueError` or a domain exception for out-of-range values
- Service methods delegate to `GraphRepository` — no business logic duplication
- Request/response models in `service_models.py` should use `pydantic.BaseModel` or `dataclasses` consistent with existing patterns
- `query_neighborhood` defaults direction to `"both"` at the service layer

## What NOT To Do
- Do NOT implement API routes — that is a separate story
- Do NOT modify `GraphRepository` protocol — that was done in E2-S01
- Do NOT modify `InMemoryGraphRepository` — that was done in E2-S02
- Do NOT add caching logic at the service layer
- Do NOT add pagination beyond what is specified (limit/offset on `search_entities`)

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
