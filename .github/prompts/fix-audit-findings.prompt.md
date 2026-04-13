---
description: "Fix findings from an audit-backend-architecture report — adds missing annotations, decorators, corrects imports, and resolves boundary violations"
agent: "agent"
argument-hint: "Paste the audit report findings section, or 'all' to re-run audit and fix"
---

# Fix Backend Audit Findings

Apply targeted code fixes for findings produced by the `/audit-backend-architecture` prompt.

**Input**: $ARGUMENTS

If the input is `all` or empty, first run the full audit yourself by following [audit-backend-architecture](.github/prompts/audit-backend-architecture.prompt.md), then fix every finding. Otherwise, parse the provided findings and fix each one.

## Required Context

Read these to understand the rules each fix must satisfy:

- [Backend instructions](.github/instructions/backend.instructions.md) — typing, coupling, testing rules
- [Architecture doc](docs/architecture.md) — module responsibilities and boundary rules
- [Copilot instructions](.github/copilot-instructions.md) — cross-module interaction paths

## Fix Procedures by Check

Apply fixes in dependency order — infrastructure fixes first, then contract fixes, then test scaffolding.

### Phase 1: Infrastructure Fixes (safe, no behavioral change)

#### Fix: Missing `from __future__ import annotations`

Add `from __future__ import annotations` as the **first** import line in the file, after any module docstring and before all other imports.

```python
"""Module docstring."""

from __future__ import annotations
# ... existing imports ...
```

Do **not** change any other code in the file. This fix is always safe.

#### Fix: Missing `@runtime_checkable` on Protocol

Add `@runtime_checkable` decorator immediately above the `class` line. Ensure `runtime_checkable` is included in the `typing` import.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class MyProtocol(Protocol):
    ...
```

#### Fix: Missing `__all__` in `__init__.py`

Add an `__all__` list at the end of the file containing every name that is imported or defined in the file. Follow the alphabetical ordering convention used in existing `__init__.py` files (see `backend/ingestion/__init__.py` for the pattern).

### Phase 2: Contract and Boundary Fixes (requires careful review)

#### Fix: Bare `Any` in Public API

Replace `Any` with the narrowest applicable type:

| Current | Replacement |
|---------|------------|
| `dict[str, Any]` in a model field for arbitrary metadata | `dict[str, object]` |
| `Any` in a function return type | The actual Pydantic model or union type being returned |
| `list[Any]` | `list[object]` or a typed union |
| `Any` in a protocol method signature | The domain type from `shared.types` or module `models.py` |

If `Any` is truly unavoidable (polymorphic containers, YAML parsing intermediates), add a `# type: ignore[explicit-any]` comment with a brief justification.

#### Fix: Cross-Module Import Violation

Determine which of these remediation patterns applies:

1. **Router importing internal models** → Change import to the module's `service_models.py` or `protocols.py`. If the needed type doesn't exist there, add a re-export or create an appropriate API-boundary model.

2. **Feature module importing from another feature module** → Identify the shared contract and move it to:
   - `shared/types.py` if it's a domain type
   - `shared/protocols.py` if it's a cross-cutting protocol
   - `events/types.py` if it's an event payload
   - The consuming module's own `protocols.py` if it defines an interface the other module should implement

3. **Service importing a concrete adapter** → Replace with the protocol import. Move concrete adapter selection to `api/dependencies.py` or `agent/coordinator.py`.

#### Fix: Service Constructor Using Concrete Types

Change the constructor parameter type annotation from the concrete class to its corresponding protocol:

```python
# Before (violation)
def __init__(self, store: InMemoryObjectStore) -> None:

# After (compliant)
def __init__(self, store: ObjectStore) -> None:
```

Update the import to pull from the protocol module, not the adapter module.

#### Fix: Adapter Protocol Signature Mismatch

Align the adapter method signature to match the protocol exactly — same parameter names, same types, same return type. If the adapter needs additional parameters, accept them in `__init__`, not in the method that implements the protocol.

### Phase 3: Model and Event Fixes

#### Fix: Pydantic Mutable Default

Replace bare mutable defaults with `Field(default_factory=...)`:

```python
# Before (violation)
tags: list[str] = []

# After (compliant)
tags: list[str] = Field(default_factory=list)
```

#### Fix: Event Not in `AnyEvent` Union

1. Verify the event class exists in `backend/events/types.py` with a `Literal` event_type.
2. Add it to the `AnyEvent` union type at the bottom of that file.
3. Add it to the decode dispatch map in `backend/events/codec.py`.

#### Fix: Model Layer Separation

If an API router imports from a module's internal `models.py`:
1. Check if an equivalent type exists in `service_models.py` — use that instead.
2. If not, create an API-boundary model in `service_models.py` that exposes only what the router needs.
3. Update the router import.

### Phase 4: Test Scaffolding

#### Fix: Missing Test Files

Create minimal test file stubs under `backend/tests/{module}/`:

```python
"""Tests for {module} models."""

from __future__ import annotations

# TODO: Add model validation tests — valid inputs, invalid inputs, edge cases.
```

Follow the pattern in existing test directories (e.g., `backend/tests/ingestion/`, `backend/tests/events/`).

Only create `__init__.py` and stub test files — do **not** write full test implementations unless the audit finding specifically says tests are needed for a particular behavior.

## Execution Rules

1. **One fix at a time.** Apply each fix, then verify no new errors are introduced before moving to the next.
2. **Preserve behavior.** Phase 1 and Phase 3 fixes must not change runtime behavior. Phase 2 fixes must preserve the same call-site contracts.
3. **Verify after fixing.** After applying all fixes, re-read each modified file to confirm correctness. Run `#tool:terminal` with `cd backend && python -m pytest tests/ -x -q` to confirm tests still pass.
4. **Report what was done.** After all fixes, produce a summary:

```markdown
## Fix Summary

| Fix | Files Modified | Status |
|-----|---------------|--------|
| Future annotations | file1.py, file2.py | done |
| @runtime_checkable | — | no findings |
| ... | ... | ... |

**Tests**: <pass/fail status>
**Remaining manual items**: <anything that couldn't be auto-fixed>
```
