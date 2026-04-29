# Story E20-S03: GNN adapter protocol — incremental graph loading and streaming inference

## Story
As a platform developer, I want the `GNNAdapterProtocol` to support incremental graph loading (adding new nodes/edges without full reload) and a streaming inference interface so GNN computation can be applied to large or growing graphs efficiently.

## Acceptance Criteria
1. `analytics/gnn/adapters/protocols.py` adds to `GNNAdapterProtocol`:
   - `add_nodes(kb_id: str, nodes: list[GNNNode]) -> None` — incrementally add nodes to the in-memory graph representation
   - `add_edges(kb_id: str, edges: list[GNNEdge]) -> None` — incrementally add edges
   - `stream_infer(kb_id: str) -> Iterator[GNNInferenceResult]` — yields partial results as inference progresses over the graph
2. `analytics/gnn/models.py` adds `GNNNode(id: str, type: str, features: dict[str, float])` and `GNNEdge(source_id: str, target_id: str, type: str, weight: float = 1.0)` if not already present.
3. The in-memory adapter implements `add_nodes` and `add_edges` (appending to an internal structure) and `stream_infer` (yields a single complete result — acceptable stub).
4. Unit tests cover: nodes and edges added are visible after add, stream_infer yields at least one result, empty graph yields zero results.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | M    | None         |

## Target Files
- `backend/analytics/gnn/adapters/protocols.py` — add `add_nodes`, `add_edges`, `stream_infer`
- `backend/analytics/gnn/models.py` — add `GNNNode`, `GNNEdge` if missing
- `backend/analytics/gnn/adapters/in_memory.py` — implement new methods
- `backend/tests/analytics/gnn/test_adapter.py` — add incremental and streaming tests

## Reference Files to Read First
- `backend/analytics/gnn/adapters/protocols.py` — current protocol
- `backend/analytics/gnn/models.py` — existing GNN models
- `backend/analytics/gnn/adapters/in_memory.py` — baseline heuristic adapter
- `backend/tests/analytics/gnn/` — existing GNN tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `stream_infer` returns a synchronous `Iterator[GNNInferenceResult]` — not async in this story
- `add_nodes` / `add_edges` must be idempotent on node/edge ID — re-adding an existing ID updates its features/weight, does not duplicate
- The in-memory adapter may hold all nodes/edges in memory; no disk persistence

## What NOT To Do
- Do not implement PyTorch Geometric or DGL adapters here — those are E7-S04 and E7-S05
- Do not add async streaming in this story
- Do not merge incremental loading into the existing `load_graph()` method — keep them separate

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/gnn tests/analytics/gnn/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
