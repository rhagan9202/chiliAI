# Story E7-S11: Self-Reinforcing Loop — Write Risk Scores Back to Graph

## Story
As a platform developer, I want the coordinator to write computed risk scores and GNN community labels back to graph entity properties.

## Acceptance Criteria
1. After risk assessment, coordinator calls `GraphService.update_entity_properties()` to set `risk_score`, `risk_level`, `risk_assessed_at`.
2. After GNN analysis, sets `community_id` and `centrality_score`.
3. Property writes are idempotent.
4. Tests verify property persistence on in-memory graph adapter.

## Priority / Size / Dependencies

| Field        | Value            |
|--------------|------------------|
| Priority     | P1               |
| Size         | M                |
| Dependencies | E7-S10, E2-S01   |

## Target Files
- `backend/agent/coordinator.py` — add graph write-back logic after GNN and risk steps in `handle_graph_updated()`
- `backend/graph/protocols.py` — add `update_entity_properties()` to `GraphServiceProtocol` if not present
- `backend/graph/service.py` — implement `update_entity_properties()` delegating to adapter
- `backend/graph/adapters/in_memory.py` — implement `update_entity_properties()` for in-memory graph
- `backend/tests/agent/test_coordinator.py` — add tests verifying graph property write-back after analytics
- `backend/tests/graph/test_in_memory_adapter.py` — add tests for idempotent property updates

## Reference Files to Read First
- `backend/agent/coordinator.py` — current coordinator with analytics pipeline from E7-S10
- `backend/graph/protocols.py` — `GraphServiceProtocol` definition
- `backend/graph/service.py` — current graph service implementation
- `backend/graph/models.py` — graph entity models
- `backend/graph/adapters/in_memory.py` — in-memory graph adapter
- `backend/analytics/gnn/service_models.py` — GNN response models (community_id, centrality_score)
- `backend/analytics/risk/service_models.py` — risk response models (risk_score, risk_level)
- `backend/tests/agent/test_coordinator.py` — existing coordinator tests
- `backend/tests/graph/` — existing graph adapter tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- Cross-module interaction via agent coordinator (permitted path)
- Follow existing patterns in the codebase
- `update_entity_properties()` must be idempotent — calling it twice with the same values produces the same result
- Properties to write: `risk_score` (float), `risk_level` (str), `risk_assessed_at` (datetime), `community_id` (str), `centrality_score` (float)
- Graph writes happen in the coordinator after each analytics step, not inside the analytics services
- Use the `GraphServiceProtocol` — do not couple to a specific adapter implementation
- Timestamps should use UTC

## What NOT To Do
- Do NOT modify analytics service implementations — they produce data, the coordinator writes it
- Do NOT create direct imports between analytics modules and the graph module
- Do NOT add API endpoints — this is coordinator-layer only
- Do NOT make graph writes block the analytics pipeline if they fail — log errors and continue
- Do NOT store analytics results anywhere other than the graph entity properties in this story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for affected files
- [ ] `pytest --cov=graph tests/graph/` >= 85% coverage for affected files
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
