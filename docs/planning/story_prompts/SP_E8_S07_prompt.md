# Story E8-S07: Monitoring stream consumer — continuous evaluation

## Story
As a platform developer, I want the worker coordinator to consume `graph.updated` and `analysis.complete` events and trigger continuous monitoring.

## Acceptance Criteria
1. `agent/coordinator.py` gains `handle_analysis_complete()` creating `MonitoringEvaluationRequest` from analysis results and calling `MonitoringService.evaluate()`.
2. Coordinator subscribes to `risk.scored` events.
3. `build_worker_dependencies()` instantiates `MonitoringService`.
4. Integration test: `risk.scored` → monitoring evaluation → `alerts.created`.
5. Monitoring failures logged but don't block pipeline.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | L    | E7-S10, E8-S01 |

## Target Files
- `backend/agent/coordinator.py` — add `handle_risk_scored()` handler, subscribe to `risk.scored` in `handle_event()`, instantiate `MonitoringService` in `build_worker_dependencies()`
- `backend/tests/agent/test_coordinator.py` — add integration test for `risk.scored` → monitoring evaluation → `alerts.created` event emission, and error-handling test verifying failures don't block pipeline

## Reference Files to Read First
- `backend/agent/coordinator.py` — existing handler pattern (`handle_documents_parsed`, `handle_documents_chunked`, `handle_entities_extracted`, `handle_entities_validated`), `build_worker_dependencies()`, `handle_event()` dispatcher
- `backend/events/types.py` — `RiskScoredEvent`, `RiskScoredReference`, `AlertsCreatedEvent`, event type union
- `backend/monitoring/service.py` — `MonitoringService` constructor, `evaluate()` method, `create_monitoring_service()` factory
- `backend/monitoring/service_models.py` — `MonitoringEvaluationRequest`, `MonitoringEvaluationResponse`
- `backend/monitoring/adapters/in_memory.py` — in-memory adapter for test instantiation
- `backend/monitoring/protocols.py` — `ObservationSourceProtocol`
- `backend/agent/models.py` — `WorkerDependencies` or equivalent dependency container
- `backend/tests/agent/test_coordinator.py` — existing integration test patterns for other handlers

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The new handler follows the same pattern as existing handlers (e.g., `handle_documents_parsed`) — receive event, extract data, call service, emit downstream event
- `handle_risk_scored()` maps `RiskScoredEvent` fields into a `MonitoringEvaluationRequest` — extract `knowledge_base_id`, observation data from `RiskScoredReference` assessments
- On success, emit `AlertsCreatedEvent` with the generated alerts
- On failure, log the error at ERROR level and return without raising — monitoring failures must not block the pipeline
- `build_worker_dependencies()` should instantiate `MonitoringService` using `create_monitoring_service()` or equivalent factory
- Add `"risk.scored"` to the event dispatch map in `handle_event()`
- The coordinator may import from `monitoring.service` and `monitoring.service_models` — this is allowed as coordinator orchestration

## What NOT To Do
- Do NOT modify the monitoring service itself — only consume it from the coordinator
- Do NOT add new event types — `RiskScoredEvent` and `AlertsCreatedEvent` already exist in `events/types.py`
- Do NOT add REST API endpoints for triggering monitoring — this is event-driven only
- Do NOT add retry logic for monitoring failures — log and continue is sufficient
- Do NOT modify event type definitions in `backend/events/types.py`
- Do NOT modify files outside `backend/agent/` and `backend/tests/agent/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
