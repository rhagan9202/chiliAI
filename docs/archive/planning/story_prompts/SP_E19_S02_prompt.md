# Story E19-S02: EventCodec auto-discovery and schema_version support

## Story
As a platform developer, I want the `EventCodec` to auto-discover registered event types via `EventBase` subclass inspection (instead of a manually maintained registry dict) and to include a `schema_version` field in serialized payloads for backward-compatible deserialization across deployments.

## Acceptance Criteria
1. `events/codec.py` replaces the manual `_REGISTRY: dict[str, type[EventBase]]` with auto-discovery: all `EventBase` subclasses that have a `event_type: ClassVar[str]` attribute are registered automatically using `__init_subclass__`.
2. `EventBase` (in `events/types.py`) uses `__init_subclass__` to self-register in a module-level registry.
3. `event_type` is a `ClassVar[str]` on each concrete event class; the codec uses it as the serialization key.
4. The serialized envelope gains `schema_version: str` (default `"1.0"`); deserialization accepts and ignores unknown schema versions gracefully.
5. The manual registry dict and its maintenance comment are removed.
6. All existing event types continue to serialise/deserialise correctly.
7. Unit tests cover: new event subclass is auto-registered, serialization includes schema_version, deserialisation of unknown schema_version succeeds.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E1-S08       |

## Target Files
- `backend/events/types.py` — add `__init_subclass__` registry on `EventBase`, add `schema_version` to envelope
- `backend/events/codec.py` — remove manual registry, use auto-discovery
- `backend/tests/events/test_codec.py` — update/add auto-discovery and schema_version tests

## Reference Files to Read First
- `backend/events/codec.py` — current codec with manual registry
- `backend/events/types.py` — `EventBase`, `EventEnvelope`, existing event types
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/tests/events/test_codec.py` — existing codec tests
- `backend/agent/coordinator.py` — how events are published and consumed

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `__init_subclass__` must only register concrete classes (skip abstract bases) — check for `event_type` presence and non-None value
- Registry must be module-level to persist across calls without re-scanning
- `schema_version` must default to `"1.0"` and be included in every serialized envelope
- Do not use metaclasses — `__init_subclass__` is sufficient

## What NOT To Do
- Do not implement schema migration or up/down conversion logic — only version tagging and graceful ignore
- Do not remove individual `event_type: ClassVar[str]` annotations from existing event classes
- Do not change the `EventEnvelope` structure beyond adding `schema_version`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=events tests/events/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
