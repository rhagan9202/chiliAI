---
description: "Audit backend modules for contract consistency, strict typing, and hexagonal boundary compliance"
agent: "agent"
argument-hint: "Module name to audit (e.g. ingestion, events) or 'all' for full backend"
---

# Backend Architecture Audit

Perform a comprehensive code audit of the Python backend for contract consistency, type model integrity, and strict compliance with hexagonal architecture boundaries.

**Scope**: $ARGUMENTS (if blank or 'all', audit every module under `backend/`)

## Required Context

Read these before auditing — they define the rules:

- [Backend instructions](.github/instructions/backend.instructions.md) — typing, coupling, testing rules
- [Architecture doc](docs/architecture.md) — module responsibilities, dependency rules, §5 package tree
- [Copilot instructions](.github/copilot-instructions.md) — cross-module interaction paths
- [Shared types](backend/shared/types.py) — domain-agnostic runtime types
- [Shared protocols](backend/shared/protocols.py) — cross-module contracts
- [Event protocols](backend/events/protocols.py) — EventBus contract
- [Event types](backend/events/types.py) — typed event payloads and AnyEvent union
- [Storage protocols](backend/storage/protocols.py) — ObjectStore contract

## Audit Procedure

For each backend module in scope, read **every** `.py` file (skip `__pycache__/`). Evaluate each file against the checks below. Record every finding.

## Audit Checks

### 1. Future Annotations Guard

Every `.py` file under `backend/` **must** have `from __future__ import annotations` as its first effective import.

- Flag: file missing the import
- Severity: **error**

### 2. Protocol Definitions

Every `Protocol` class defined in the backend **must** be decorated with `@runtime_checkable`.

- Flag: `Protocol` subclass without `@runtime_checkable`
- Severity: **error**

### 3. Bare `Any` Usage

Untyped `Any` should not appear in public APIs, protocol method signatures, or model field types. Acceptable exceptions:

- `shared/types.py` domain-agnostic property containers (`Entity.properties`, `Relationship.properties`) — these are intentionally polymorphic
- Internal helper functions not part of the module's public contract
- YAML/JSON deserialization intermediates in `config/loader.py`

For all other uses:

- Flag: bare `Any` in public function signature, protocol method, or Pydantic model field
- Severity: **warning** (with suggestion for a narrower type)

### 4. Cross-Module Import Boundaries

Feature modules (`ingestion/`, `graph/`, `vectorstore/`, `embeddings/`, `rag/`, `llm/`, `analytics/`, `monitoring/`) must **never** import directly from each other. Allowed cross-module import sources:

| Importing module | May import from |
|---|---|
| Any feature module | `shared.*`, `events.types`, `events.protocols`, `storage.protocols`, `storage.models` |
| `api/` routers | `api.dependencies`, feature module `protocols.py` and `service_models.py` only |
| `api/dependencies.py` | Any module (it is the DI wiring layer) |
| `agent/coordinator.py` | Any module (it is the worker wiring layer) |
| `config/` | `shared.types` only |

- Flag: import that violates the table above
- Severity: **error**

### 5. Service Constructor Injection

Every service class (the primary orchestration class in a module's `service.py`) must receive **all** external dependencies through `__init__` parameters typed to their protocol, not concrete implementations.

- Flag: service constructor accepting a concrete class instead of its protocol
- Flag: service importing and instantiating its own dependencies internally
- Severity: **error**

### 6. Adapter Protocol Conformance

Every concrete adapter under an `adapters/` sub-package must structurally satisfy the protocol it implements. Verify method signatures match (name, parameters, return types).

- Flag: adapter method signature that diverges from its protocol
- Flag: adapter missing a method required by its protocol
- Severity: **error**

### 7. Model Layer Separation

Each module should separate:
- **Internal workflow models** (`models.py`) — used within the module and between its internal components
- **API boundary models** (`service_models.py`) — used at the service protocol boundary, consumed by `api/` routers

- Flag: API router importing directly from a module's internal `models.py` instead of `service_models.py` or `protocols.py`
- Flag: internal orchestration code using API boundary models where internal models exist
- Severity: **warning**

### 8. Event Type Consistency

All events published by services must:
- Be defined in `backend/events/types.py` as a subclass of `EventBase` with a `Literal` event_type
- Be included in the `AnyEvent` union type
- Use typed reference models (not raw dicts) for event payloads

- Flag: event published that isn't in `AnyEvent`
- Flag: event payload using `dict` instead of a typed Pydantic model
- Severity: **error**

### 9. Pydantic Model Hygiene

For all Pydantic `BaseModel` subclasses:
- Mutable default values must use `Field(default_factory=...)`
- Cross-field invariants should use `@model_validator`
- Numeric constraints should use `Field(ge=0)`, `Field(gt=0)`, etc.
- `__all__` exports must be present in `__init__.py` files

- Flag: mutable default without `Field(default_factory=...)`
- Flag: missing `__all__` in a package `__init__.py`
- Severity: **warning**

### 10. Test Coverage Completeness

For each module in scope, verify corresponding test files exist under `backend/tests/{module}/`:
- Model validation tests
- Service unit tests
- Adapter protocol conformance tests (if adapters exist)

- Flag: module with no test directory
- Flag: module with service implementation but no service tests
- Severity: **warning**

## Output Format

Produce a structured audit report with these sections:

```markdown
# Backend Architecture Audit Report

**Scope**: <modules audited>
**Files scanned**: <count>
**Date**: <date>

## Summary

| Check | Errors | Warnings | Pass |
|-------|--------|----------|------|
| Future annotations | ... | — | ... |
| Protocol @runtime_checkable | ... | — | ... |
| Bare Any usage | — | ... | ... |
| Cross-module boundaries | ... | — | ... |
| Constructor injection | ... | — | ... |
| Adapter conformance | ... | — | ... |
| Model layer separation | — | ... | ... |
| Event type consistency | ... | — | ... |
| Pydantic model hygiene | — | ... | ... |
| Test coverage | — | ... | ... |

**Total**: X errors, Y warnings across Z files

## Findings

### Errors (must fix)

1. **[file.py](path) — Check Name**: Description of violation and suggested fix.

### Warnings (should fix)

1. **[file.py](path) — Check Name**: Description and recommendation.

### Observations

- Architectural notes, patterns worth documenting, or emerging risks.

## Recommendations

Prioritized action items to bring the backend into full compliance.
```
