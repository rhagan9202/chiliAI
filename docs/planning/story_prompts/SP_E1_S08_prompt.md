# Story E1-S08: Enrich event envelope with correlation_id, source, and schema_version

## Story
As a platform developer, I want every event to carry a `correlation_id`, `source`, and `schema_version`, so that distributed traces can be correlated.

## Acceptance Criteria
1. `EventBase` in `events/types.py` has `correlation_id: str`, `source: str | None = None`, `schema_version: int = 1`.
2. Worker pipeline handlers propagate `correlation_id` from incoming to downstream events.
3. Existing event construction still works.
4. At least one test verifies correlation_id propagation.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/events/types.py` — add `correlation_id`, `source`, `schema_version` fields to `EventBase`
- `backend/agent/coordinator.py` — update pipeline handlers to propagate `correlation_id` from incoming events to downstream events
- `backend/tests/events/test_types.py` — add tests for new fields, default generation, and serialization
- `backend/tests/agent/test_coordinator.py` — add test verifying `correlation_id` propagation through pipeline stages

## Reference Files to Read First
- `backend/events/types.py` — current `EventBase` model and all event subclasses
- `backend/agent/coordinator.py` — current pipeline handler implementations and how events flow between stages
- `backend/shared/utils.py` — `generate_id()` utility for default `correlation_id` generation
- `backend/events/protocols.py` — `EventBus` protocol for understanding event publish/subscribe
- `backend/tests/events/test_types.py` — existing event test patterns
- `backend/tests/agent/test_coordinator.py` — existing coordinator test patterns (if present)

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `correlation_id` must default to a new UUID via `Field(default_factory=generate_id)` using `shared.utils.generate_id`
- `source` identifies the producing service/module — it is optional and not auto-populated
- `schema_version` defaults to `1` for forward-compatible event envelope versioning
- Existing event construction (without passing `correlation_id`) must still work due to the default factory
- Remove the TODO comment in `EventBase` about correlation_id/source/schema_version since they will be implemented
- Propagation means: when a handler receives event A and emits event B, B.correlation_id = A.correlation_id

## What NOT To Do
- Do NOT change event_type values or existing field names on any event subclass
- Do NOT modify the `EventBus` protocol or transport layer
- Do NOT add distributed tracing infrastructure (OpenTelemetry, etc.) — that is a separate concern
- Do NOT modify event codec or serialization in `events/codec.py` unless strictly necessary
- Do NOT add new event types — only enrich the base envelope
- Do NOT modify any files outside the target files listed above

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=events tests/events/` >= 85% coverage for events module
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for agent module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
