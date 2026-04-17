# Story E7-S10: Wire Analytics into the Coordinator Event Chain

## Story
As a platform developer, I want the worker coordinator to consume `graph.updated` events and trigger the analytics pipeline.

## Acceptance Criteria
1. `agent/coordinator.py` gains `handle_graph_updated()` triggering GNN → risk → explainability.
2. `build_worker_dependencies()` instantiates analytics services.
3. Coordinator subscribes to `graph.updated` and dispatches to analytics handler.
4. Integration test: `graph.updated` → GNN → risk → explainability → `alerts.created`.
5. Analytics failures logged, don't block pipeline — produce `analysis.failed` events.

## Priority / Size / Dependencies

| Field        | Value          |
|--------------|----------------|
| Priority     | P0             |
| Size         | L              |
| Dependencies | E7-S06, E1-S07 |

## Target Files
- `backend/agent/coordinator.py` — add `handle_graph_updated()` method; subscribe to `graph.updated` event; wire analytics pipeline
- `backend/agent/service.py` — update `build_worker_dependencies()` to instantiate GNN, risk, explainability services
- `backend/agent/models.py` — add any event types needed (e.g., `AnalysisFailed`)
- `backend/events/types.py` — add `graph.updated`, `alerts.created`, `analysis.failed` event types if not present
- `backend/tests/agent/test_coordinator.py` — integration test for full event chain
- `backend/tests/agent/test_analytics_handler.py` — unit tests for `handle_graph_updated()` including failure paths

## Reference Files to Read First
- `backend/agent/coordinator.py` — current coordinator implementation and event handling patterns
- `backend/agent/service.py` — current `build_worker_dependencies()` and service wiring
- `backend/agent/protocols.py` — coordinator protocol definitions
- `backend/agent/models.py` — existing event/model types
- `backend/events/types.py` — existing event type definitions
- `backend/events/protocols.py` — event bus protocol
- `backend/analytics/gnn/service.py` — GNN service interface
- `backend/analytics/risk/service.py` — risk service interface (post E7-S06 strategy refactor)
- `backend/analytics/explainability/service.py` — explainability service interface
- `backend/analytics/gnn/protocols.py` — GNN service protocol
- `backend/analytics/risk/protocols.py` — risk service protocol
- `backend/analytics/explainability/protocols.py` — explainability service protocol
- `backend/tests/agent/` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- Cross-module interaction is allowed here via the agent coordinator pattern (one of the three permitted paths)
- Follow existing patterns in the codebase
- Analytics services are injected into the coordinator via constructor or `build_worker_dependencies()`
- Pipeline order is strict: GNN → risk → explainability
- Each step's output feeds the next step's input
- Analytics failures must be caught, logged, and produce `analysis.failed` events — never propagate as unhandled exceptions
- The `alerts.created` event is emitted only if the full pipeline succeeds
- Use existing event bus protocol for subscribing and publishing

## What NOT To Do
- Do NOT modify the analytics service implementations (GNN, risk, explainability)
- Do NOT create direct imports between analytics sub-modules — the coordinator orchestrates
- Do NOT let analytics failures crash the coordinator or block other event processing
- Do NOT add API endpoints — this is worker/coordinator only
- Do NOT hardcode service implementations — use protocol-typed dependencies

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for affected files
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
