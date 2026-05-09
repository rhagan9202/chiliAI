# Story E21-S01: InMemoryGraphRepository — referential integrity checks

## Story
As a platform developer, I want the `InMemoryGraphRepository` to enforce referential integrity so that relationships referencing non-existent entities raise a descriptive error, preventing silent data corruption in tests.

## Acceptance Criteria
1. `graph/adapters/in_memory.py` checks, during `upsert_relationships()`, that both `source_entity_id` and `target_entity_id` exist in the store for the given `kb_id` before persisting the relationship.
2. If either endpoint is missing, raise `GraphIntegrityError(relationship_id, missing_entity_id)`.
3. `graph/exceptions.py` adds `GraphIntegrityError(relationship_id: str, missing_entity_id: str)`.
4. The check is skipped when `allow_dangling: bool = False` is passed as `True` to `upsert_relationships()` (opt-out for bulk imports that guarantee entity pre-existence).
5. Unit tests cover: valid relationship accepted, missing source raises `GraphIntegrityError`, missing target raises, allow_dangling=True skips check.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/graph/adapters/in_memory.py` — add referential integrity check in `upsert_relationships()`
- `backend/graph/exceptions.py` — add `GraphIntegrityError`
- `backend/tests/graph/test_in_memory.py` — add integrity check tests

## Reference Files to Read First
- `backend/graph/adapters/in_memory.py` — current `InMemoryGraphRepository`
- `backend/graph/exceptions.py` — existing graph exception hierarchy
- `backend/graph/protocols.py` — `GraphRepository` protocol and `upsert_relationships()` signature
- `backend/graph/models.py` — `Relationship` model
- `backend/tests/graph/test_in_memory.py` — existing graph repository tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `GraphIntegrityError` must be a subclass of the existing graph exception base class
- The check must use the same `kb_id`-scoped entity store as `upsert_entities()` — do not check across KB boundaries
- `allow_dangling` must default to `False` to preserve strict behavior as the baseline

## What NOT To Do
- Do not add referential integrity to the Neo4j adapter here — that is a separate story
- Do not check integrity on entity upsert (only on relationship upsert)
- Do not cascade-delete relationships when entities are deleted — that is a future story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=graph tests/graph/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
