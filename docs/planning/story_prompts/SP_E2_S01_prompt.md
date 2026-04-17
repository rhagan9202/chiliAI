# Story E2-S01: Extend GraphRepository protocol with read/query methods

## Story
As a platform developer, I want the `GraphRepository` protocol to define `get_entity`, `get_neighbors`, `get_entities_by_type`, `search_entities`, `count_entities`, `count_relationships`, and `delete_entity`, so that all graph adapters provide a consistent query surface.

## Acceptance Criteria
1. `graph/adapters/protocols.py` adds: `get_entity(kb_id, entity_id) -> Entity | None`, `get_neighbors(kb_id, entity_id, depth: int, direction: Literal["in", "out", "both"]) -> SubgraphResult`, `get_entities_by_type(kb_id, entity_type, limit, offset) -> list[Entity]`, `search_entities(kb_id, query: str, limit) -> list[Entity]`, `count_entities(kb_id) -> int`, `count_relationships(kb_id) -> int`, `delete_entity(kb_id, entity_id) -> None`, `delete_relationship(kb_id, relationship_id) -> None`.
2. `graph/models.py` defines `SubgraphResult` (entities: list[Entity], relationships: list[Relationship]) and `GraphMetrics` (entity_count, relationship_count, avg_degree).
3. Protocol is `@runtime_checkable`.

## Priority / Size / Dependencies
- **Priority:** P0
- **Size:** S
- **Dependencies:** None

## Target Files
- `backend/graph/adapters/protocols.py` — add read/query/delete method signatures to `GraphRepository`
- `backend/graph/models.py` — add `SubgraphResult` and `GraphMetrics` dataclasses
- `backend/tests/graph/test_models.py` — add tests for new model types

## Reference Files to Read First
- `backend/graph/adapters/protocols.py` — current `GraphRepository` protocol definition
- `backend/graph/models.py` — existing graph domain models
- `backend/shared/types.py` — `Entity`, `Relationship` definitions
- `backend/graph/exceptions.py` — existing graph exceptions
- `docs/architecture.md` — §5 graph module responsibilities

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Protocol must remain `@runtime_checkable`
- Use `typing.Literal["in", "out", "both"]` for direction parameter
- `SubgraphResult` is reused by the investigation workbench neighborhood query and RAG context expansion — keep it general
- Import `Entity` and `Relationship` from `shared/types.py`, not from local models

## What NOT To Do
- Do NOT implement the methods in any adapter — this story is protocol-only
- Do NOT add service-layer methods — that is E2-S03
- Do NOT add optional parameters beyond what is specified in the acceptance criteria
- Do NOT create new exception types — reuse existing ones from `graph/exceptions.py`
- Do NOT change signatures of existing protocol methods

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
