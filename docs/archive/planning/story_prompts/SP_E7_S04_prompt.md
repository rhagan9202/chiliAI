# Story E7-S04: GNN — Community Detection (Louvain)

## Story
As a platform developer, I want the GNN service to detect communities in the graph snapshot.

## Acceptance Criteria
1. `GnnAnalysisResponse` gains `communities: list[GnnCommunity]` with `community_id`, `member_entity_ids`, `density`.
2. `GnnService.analyze()` runs community detection after node scoring.
3. `GnnNodeScore.cluster_id` set to detected community ID.
4. Tests verify on graph with two clearly separated clusters.

## Priority / Size / Dependencies

| Field        | Value |
|--------------|-------|
| Priority     | P2    |
| Size         | M     |
| Dependencies | None  |

## Target Files
- `backend/analytics/gnn/models.py` — add `GnnCommunity` model with `community_id`, `member_entity_ids`, `density`
- `backend/analytics/gnn/service_models.py` — add `communities` field to `GnnAnalysisResponse`; add `cluster_id` to `GnnNodeScore` if not present
- `backend/analytics/gnn/service.py` — add community detection step in `analyze()` after node scoring
- `backend/tests/analytics/gnn/test_service.py` — add tests with two-cluster graph topology

## Reference Files to Read First
- `backend/analytics/gnn/service.py` — current GNN service implementation
- `backend/analytics/gnn/service_models.py` — current request/response models
- `backend/analytics/gnn/models.py` — current domain models (GnnNodeScore, etc.)
- `backend/analytics/gnn/protocols.py` — service protocol definition
- `backend/analytics/gnn/exceptions.py` — existing exception types
- `backend/tests/analytics/gnn/test_service.py` — existing test patterns
- `backend/analytics/gnn/adapters/` — existing adapter implementations

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use `networkx.community` Louvain method (`networkx.community.louvain_communities`)
- `networkx` should already be a dependency — verify in `pyproject.toml`
- Community detection runs after node scoring to avoid altering score computation
- `density` should be computed per community subgraph using `networkx.density()`
- `GnnCommunity` is a domain model in `models.py`, not a service model

## What NOT To Do
- Do NOT modify existing node scoring logic
- Do NOT import from other analytics sub-modules (timeseries, risk, explainability)
- Do NOT add API endpoints — this is service-layer only
- Do NOT use external community detection libraries beyond `networkx`
- Do NOT make community detection optional in this story — it always runs when `analyze()` is called

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=analytics/gnn tests/analytics/gnn/` >= 85% coverage
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `GnnCommunity(community_id, member_entity_ids,
density)` was added to `analytics/gnn/models.py`. `_detect_communities()`
runs `networkx.community.louvain_communities` with a fixed seed against the
service-built graph and computes per-subgraph density via
`networkx.density()`. Detected community IDs are merged back onto each
`ScoredNode.cluster_id` so consumers see consistent grouping.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/analytics/gnn/` includes a
two-cluster topology test verifying member partitioning and density
between 0 and 1; sub-module coverage 97%.
