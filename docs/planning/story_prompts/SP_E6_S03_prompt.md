# Story E6-S03: Production GraphContextExpander adapter — delegate to GraphService

## Story
As a platform developer, I want a `ServiceGraphContextExpander` adapter that delegates `expand` to the `GraphService`.

## Acceptance Criteria
1. `rag/adapters/graph_bridge.py` implements `GraphContextExpanderProtocol`.
2. Accepts `GraphServiceProtocol`, extracts entity IDs from context_items, calls `get_neighbors` per entity (depth configurable, default 1), assembles `GraphContext`.
3. Unit test verifies graph traversal delegation and `GraphContext` assembly.
4. If graph service returns no neighbors, returns `GraphContext` with empty summary — no error.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P1      |
| Size         | M       |
| Dependencies | E2-S01, E2-S02 |

## Target Files
- `backend/rag/adapters/graph_bridge.py` — new file implementing `ServiceGraphContextExpander`
- `backend/rag/adapters/__init__.py` — re-export `ServiceGraphContextExpander`
- `backend/tests/rag/test_graph_bridge.py` — unit tests for the adapter

## Reference Files to Read First
- `backend/rag/protocols.py` — `GraphContextExpanderProtocol` definition
- `backend/rag/adapters/in_memory.py` — existing in-memory adapter pattern to follow
- `backend/rag/adapters/protocols.py` — adapter-level protocol definitions
- `backend/rag/models.py` — `GraphContext`, `RetrievedContextItem`, and related domain models
- `backend/graph/protocols.py` — `GraphServiceProtocol` (the dependency)
- `backend/graph/service_models.py` — graph service request/response types
- `backend/graph/models.py` — graph domain models (nodes, edges, neighbors)

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The adapter must depend on `GraphServiceProtocol` (abstract), never on a concrete graph adapter
- Import `GraphServiceProtocol` from `graph.protocols` — allowed cross-module boundary via protocol dependency injection
- Depth parameter must be configurable (constructor or method param), defaulting to 1
- Entity ID extraction from `RetrievedContextItem` metadata must be robust — handle missing entity IDs gracefully
- Return `GraphContext` with empty summary when no neighbors found — never raise an error for "no graph data"

## What NOT To Do
- Do NOT instantiate or import any concrete `GraphService` implementation — accept the protocol via constructor injection
- Do NOT add new protocols or change `GraphContextExpanderProtocol` — implement it as-is
- Do NOT add HTTP/network calls — this is a pure delegation adapter
- Do NOT modify `graph/` module files
- Do NOT raise exceptions when graph returns no neighbors — return empty `GraphContext`
- Do NOT implement recursive graph traversal beyond the configurable depth — delegate depth to the graph service call
- Do NOT assume entity IDs are always present in context item metadata — handle missing IDs by skipping those items

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `rag/adapters/graph_bridge.py` introduces
`ServiceGraphContextExpander`, which extracts entity IDs from
`RetrievedContextItem.metadata` (probing `entity_id`, `entityId`, then
`entity`), deduplicates them, and calls `GraphServiceProtocol.query_neighborhood`
once per entity at a constructor-configured `depth` (default 1). Returned
`SubgraphResult` entities and relationships are folded into a `GraphContext`
with `GraphContextNode`/`GraphContextEdge` instances; nodes and edges are
deduplicated by ID. When no entities are extractable or all neighborhood
queries return empty subgraphs, the adapter returns a `GraphContext` with
an empty summary and never raises. Constructor rejects negative depth.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/rag/test_graph_bridge.py
tests/rag/test_llm_bridge.py -q` passed (20 tests). `.venv/bin/ruff check
rag/adapters/graph_bridge.py rag/adapters/llm_bridge.py
tests/rag/test_graph_bridge.py tests/rag/test_llm_bridge.py` clean.
`.venv/bin/pyright rag/adapters/graph_bridge.py rag/adapters/llm_bridge.py
tests/rag/test_graph_bridge.py tests/rag/test_llm_bridge.py` reported 0 errors.
Full `tests/rag/` suite (46 tests) passes.
