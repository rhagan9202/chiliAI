# Story E3-S08: Extend ObjectStore Protocol with delete, exists, list_keys

**Status:** Complete on April 25, 2026.

## Story
As a platform developer, I want the `ObjectStore` protocol to include `delete(key)`, `exists(key) -> bool`, and `list_keys(prefix) -> list[str]`.

## Acceptance Criteria
1. `storage/protocols.py` adds `delete`, `exists`, and `list_keys` to the `ObjectStore` protocol.
2. `InMemoryObjectStore` implements all three new methods.
3. Existing tests pass; new unit tests cover each method on the in-memory adapter.

## Priority / Size / Dependencies
- **Priority:** P0
- **Size:** S
- **Dependencies:** None

## Target Files
- `backend/storage/protocols.py` — **modify** — add `delete`, `exists`, `list_keys` methods to `ObjectStore` protocol
- `backend/storage/adapters/in_memory.py` — **modify** — implement `delete`, `exists`, `list_keys` on `InMemoryObjectStore`
- `backend/tests/storage/test_in_memory.py` — **modify or create** — add unit tests for `delete`, `exists`, `list_keys` on the in-memory adapter

## Reference Files to Read First
- `backend/storage/protocols.py` — current `ObjectStore` protocol definition (to understand existing methods)
- `backend/storage/models.py` — storage domain models
- `backend/storage/adapters/in_memory.py` — current `InMemoryObjectStore` implementation
- `backend/tests/storage/` — existing storage tests (to understand test patterns and ensure no regressions)
- `backend/shared/types.py` — shared domain types

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Protocol methods must use consistent signatures:
  - `delete(self, key: str) -> None` — remove object by key; no-op or raise if not found (match existing convention)
  - `exists(self, key: str) -> bool` — return `True` if the key exists
  - `list_keys(self, prefix: str) -> list[str]` — return all keys matching the prefix
- Methods must be `async` if the existing protocol methods are `async`, or sync if existing methods are sync — match the existing pattern
- This is a **P0 blocker** for E3-S06 and E3-S07 — ensure the protocol changes are backward-compatible

## What NOT To Do
- Do not break existing protocol methods (`put_bytes`, `get_bytes`) — only add new ones
- Do not change method signatures of existing protocol methods
- Do not add methods beyond `delete`, `exists`, `list_keys` — scope is intentionally limited
- Do not modify any adapter other than `InMemoryObjectStore` — other adapters (S3, local FS) are separate stories
- Do not add dependencies — this is protocol and in-memory only
- Do not remove or rename existing tests

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Existing tests still pass (no regressions)
- [x] New tests written and passing for `delete`, `exists`, `list_keys`
- [x] `pytest --cov=storage tests/storage/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Notes
- `ObjectStore` now exposes synchronous `delete`, `exists`, and `list_keys` methods.
- `InMemoryObjectStore.delete()` treats missing keys as a no-op to align with S3-style delete semantics.
- `InMemoryObjectStore.list_keys()` returns deterministic sorted keys and supports `list_keys("")` for all keys.

## Validation Notes
- `pytest tests/storage/ --cov=storage --cov-report=term-missing` passed with 15 tests and 100% storage coverage.
- `ruff check storage tests/storage` passed.
- `pyright storage tests/storage` passed with 0 errors.
