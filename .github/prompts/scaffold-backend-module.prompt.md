---
description: "Scaffold a new hexagonal backend service module with ports, adapters, models, protocols, service, tests, and TODO stubs"
agent: "agent"
argument-hint: "Module name (e.g. graph, vectorstore, embeddings, rag, llm)"
---

# Scaffold a New Backend Service Module

Create a complete backend service module at `backend/{moduleName}/` following the hexagonal architecture patterns established in `backend/ingestion/`.

**Module name**: $ARGUMENTS

## Required Reading

Before generating any code, read these files to understand conventions and the exemplar patterns:

- [Backend instructions](.github/instructions/backend.instructions.md) — typing, coupling, and testing rules
- [Architecture doc](docs/architecture.md) — module responsibilities and boundaries
- [Ingestion protocols](backend/ingestion/protocols.py) — service protocol exemplar
- [Ingestion models](backend/ingestion/models.py) — internal transport model exemplar  
- [Ingestion service_models](backend/ingestion/service_models.py) — API boundary model exemplar
- [Ingestion service](backend/ingestion/service.py) — service implementation exemplar
- [Ingestion orchestrator protocols](backend/ingestion/orchestrators/protocols.py) — internal orchestration contracts
- [Ingestion parser protocols](backend/ingestion/parsers/protocols.py) — adapter contracts exemplar
- [Ingestion parser registry](backend/ingestion/parsers/registry.py) — adapter registry exemplar
- [Shared types](backend/shared/types.py) — domain-agnostic runtime types
- [Shared protocols](backend/shared/protocols.py) — cross-module contracts
- [Event types](backend/events/types.py) — typed event payloads
- [Event protocols](backend/events/protocols.py) — EventBus contract
- [Storage protocols](backend/storage/protocols.py) — ObjectStore contract

Also consult `docs/architecture.md` §5 for the module's position in the package tree and its responsibility description.

## File Structure to Generate

```
backend/{moduleName}/
├── __init__.py              # Public exports with explicit __all__
├── models.py                # Internal transport and workflow Pydantic models
├── service_models.py        # API-boundary request/response Pydantic models
├── protocols.py             # Service-level Protocol (runtime_checkable)
├── service.py               # Core service implementation (constructor injection)
├── exceptions.py            # Module-specific exception hierarchy
├── adapters/
│   ├── __init__.py          # Adapter package exports
│   ├── protocols.py         # Adapter-level Protocols (e.g., store, client)
│   └── in_memory.py         # In-memory adapter for tests and local dev
└── (optional sub-packages for orchestration, internal concerns)
```

Also generate:
```
backend/tests/{moduleName}/
├── __init__.py
├── test_models.py           # Model validation tests
├── test_service.py          # Service unit tests with faked adapters
└── test_in_memory_adapter.py # Adapter contract tests
```

## Architecture Rules (Enforced)

### Hexagonal / Ports-and-Adapters
- **Protocols as ports**: Every external dependency the module needs (stores, clients, buses) is expressed as a `typing.Protocol` with `@runtime_checkable` in either `protocols.py` (service-level) or `adapters/protocols.py` (adapter-level).
- **Constructor injection**: The service class receives all dependencies through `__init__` parameters typed to their protocol. No global state, no hardcoded implementations.
- **Adapters implement protocols**: Each concrete adapter lives under `adapters/` and satisfies the protocol contract. Start with an `in_memory.py` adapter suitable for tests.

### Strict Typing (Python 3.12)
- `from __future__ import annotations` at the top of every file.
- Full type annotations on all public APIs and non-trivial internals.
- No untyped `Any` — use explicit domain types from `shared.types` or module-local models.
- Code must be compatible with `pyright --strict`.

### Models
- Use Pydantic `BaseModel` for all data structures.
- Use `Field(default_factory=...)` for mutable defaults.
- Use `model_validator` for cross-field invariants.
- Separate internal workflow models (`models.py`) from API-boundary models (`service_models.py`).
- Use `model_copy(update={...})` for immutable state transitions.

### Cross-Module Interaction
- Import only from `shared/` (types, protocols, utils) and `events/` (types, protocols).
- **Never** import directly from another feature module (e.g., don't import from `ingestion`).
- Publish typed events via the `EventBus` protocol for downstream consumers.

### Event Integration
- Define any new event payload types needed in `backend/events/types.py` (follow the `EventBase` pattern with `Literal` event_type).
- Add new events to the `AnyEvent` union type.
- Service publishes events through the injected `EventBus` — never instantiate an event bus directly.

### Error Handling
- Define a module-specific base exception in `exceptions.py`.
- Derive specific exceptions from the base.
- Service methods may return structured failure types (like `DocumentParseFailure`) for partial-failure batch semantics instead of raising.

### Testing
- pytest with ≥ 85% coverage for the module.
- Use the in-memory adapter and faked dependencies — no network, no database, no real LLM calls.
- Test model validation (valid and invalid inputs).
- Test service orchestration logic.
- Test adapter protocol conformance.

## TODO Stub Convention

For any functionality that is recognized as needed but not yet implemented, use this exact pattern:

```python
# TODO: <concise description of what needs to be implemented or extended>
raise NotImplementedError("<same description>")
```

For methods with a return type, add a brief stub docstring explaining the intent:

```python
def process(self, input: InputModel) -> OutputModel:
    """Process input through the pipeline.

    TODO: Implement full processing pipeline — currently a stub.
    """
    # TODO: Implement processing logic
    raise NotImplementedError("Processing logic not yet implemented.")
```

Mark every placeholder, deferred integration, or future extension point with a `# TODO:` so they are discoverable via search.

## Generation Checklist

After scaffolding, verify:
- [ ] Every `.py` file has `from __future__ import annotations`
- [ ] All protocols use `@runtime_checkable`
- [ ] Service constructor accepts all deps as protocol-typed params
- [ ] `__init__.py` files have explicit `__all__` lists
- [ ] No cross-feature-module imports (only `shared.*`, `events.*`, `storage.*`)
- [ ] In-memory adapter exists and satisfies protocol
- [ ] Test files exist with at least model and service test stubs
- [ ] All unimplemented functionality has `# TODO:` markers
- [ ] Exception hierarchy defined in `exceptions.py`
- [ ] New event types (if any) added to `events/types.py` and `AnyEvent` union
