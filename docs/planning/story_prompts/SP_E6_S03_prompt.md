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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
