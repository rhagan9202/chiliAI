# Story E19-S01: InMemory event bus — consumer groups and pending message state

## Story
As a platform developer, I want the `InMemoryEventBus` adapter to track consumer groups and pending message state so that integration tests can accurately mirror Redis Streams semantics (messages are only consumed once per group, redelivered on failure).

## Acceptance Criteria
1. `events/adapters/in_memory.py` refactors `InMemoryEventBus` to track consumers per group: `consume(event_types, group_id, consumer_id)` returns an event only if it has not been acknowledged by `group_id`.
2. `acknowledge(event_id, group_id)` marks the event as delivered to `group_id` so it won't be redelivered.
3. A new `get_pending(group_id) -> list[EventEnvelope]` method returns events consumed but not yet acknowledged by `group_id`.
4. Events are still delivered in arrival order per group; a single event may be delivered to multiple independent groups (pub-sub fan-out).
5. Unit tests cover: single group consumes once, two groups each receive their own copy, pending list grows on consume and shrinks on acknowledge, unacknowledged message redelivered after consume timeout stub.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | None         |

## Target Files
- `backend/events/adapters/in_memory.py` — refactor `InMemoryEventBus` with consumer group tracking
- `backend/tests/events/test_in_memory.py` — add consumer group and pending state tests

## Reference Files to Read First
- `backend/events/adapters/in_memory.py` — current `InMemoryEventBus`
- `backend/events/protocols.py` — `EventBus` protocol (subscribe, publish, consume, acknowledge)
- `backend/events/types.py` — `EventEnvelope` model
- `backend/tests/events/` — existing event bus tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- The refactor must be backward-compatible: existing tests that don't use group semantics must still pass
- Consumer group state is in-process only (dict); no persistence
- `get_pending` is an in-memory-adapter-specific method (not on `EventBus` protocol) — accessed via the concrete type in tests

## What NOT To Do
- Do not implement Redis Streams consumer group protocol (XGROUP, XREADGROUP) — this is an in-memory simulation only
- Do not break existing test patterns for non-group-aware consumers
- Do not add dead-letter queue logic here — that is E4-S04

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=events tests/events/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
