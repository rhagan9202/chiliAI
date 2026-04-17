# Story E8-S05: Alert lifecycle state machine

## Story
As a platform developer, I want `Alert` to implement a state machine with transitions open → acknowledged → investigating → resolved → dismissed.

## Acceptance Criteria
1. `Alert.status` typed as `Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]` (confirm/extend from E1-S10).
2. `transition_alert_status(alert, new_status, actor)` enforces valid transitions and updates `updated_at`, `resolved_by`, `resolution_notes`.
3. Invalid transitions raise `AlertLifecycleError`.
4. Valid transitions: open→acknowledged, open→dismissed, acknowledged→investigating, investigating→resolved, investigating→dismissed, any→open (reopen).
5. Tests verify each valid transition and at least two invalid transitions.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E1-S10       |

## Target Files
- `backend/monitoring/exceptions.py` — add `AlertLifecycleError` exception class
- `backend/monitoring/service.py` — add `transition_alert_status(alert: Alert, new_status: str, actor: str, *, resolution_notes: str | None = None) -> Alert` function enforcing valid transitions
- `backend/tests/monitoring/test_service.py` — add tests for all valid transitions and at least two invalid transitions

## Reference Files to Read First
- `backend/shared/types.py` — `Alert` model with `status`, `updated_at`, `resolved_by`, `resolution_notes` fields (from E1-S10)
- `backend/monitoring/service.py` — current service structure and helper functions
- `backend/monitoring/exceptions.py` — existing exception hierarchy (`MonitoringError`, `MonitoringConfigurationError`, `MonitoringSourceError`)
- `backend/shared/utils.py` — `utc_now()` utility for setting `updated_at`
- `backend/tests/monitoring/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `AlertLifecycleError` should inherit from `MonitoringError` for consistent exception hierarchy
- Valid transition map (define as a module-level constant):
  - `"open"` → `{"acknowledged", "dismissed"}`
  - `"acknowledged"` → `{"investigating", "open"}`
  - `"investigating"` → `{"resolved", "dismissed", "open"}`
  - `"resolved"` → `{"open"}`
  - `"dismissed"` → `{"open"}`
- The "any → open" reopen semantics means every status can transition to `"open"`
- `transition_alert_status` is a pure function (not a method on MonitoringService) — it takes an Alert, validates the transition, and returns a new Alert with updated fields
- When transitioning to `"resolved"`, `resolved_by` is set to `actor` and `resolution_notes` is set if provided
- When transitioning to any status, `updated_at` is set to `utc_now()`
- The function returns a new `Alert` instance (Pydantic `model_copy(update=...)`) rather than mutating in place

## What NOT To Do
- Do NOT modify `backend/shared/types.py` — the `Alert.status` Literal type was established in E1-S10
- Do NOT add transition history/audit log — that is future work
- Do NOT add API endpoints for status transitions — that is a separate API story
- Do NOT add event emission on status change — that can be layered later
- Do NOT add notification/webhook triggers on transitions
- Do NOT modify files outside `backend/monitoring/` and `backend/tests/monitoring/`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=monitoring tests/monitoring/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
