# Story E10-S04: Backend test coverage gap closure — graph module

## Story
As a platform developer, I want ≥ 85% test coverage for the `graph/` module, so that graph operations, queries, and error paths are validated.

## Acceptance Criteria
1. `pytest --cov=graph tests/graph/` reports ≥ 85% line coverage.
2. Tests cover: upsert entities, upsert relationships, get_entity, get_neighbors, search_entities, count operations, delete operations, idempotent upserts, error paths.
3. Tests cover the query methods added in E2-S01.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E2-S01       |

## Target Files
- `backend/tests/graph/test_service.py` — graph service tests
- `backend/tests/graph/test_adapters.py` — adapter tests (in-memory)
- `backend/tests/graph/test_models.py` — model validation tests
- `backend/tests/graph/conftest.py` — shared fixtures

## Reference Files to Read First
- `backend/graph/service.py` — graph service implementation
- `backend/graph/protocols.py` — graph protocol definitions
- `backend/graph/models.py` — entity/relationship models
- `backend/graph/exceptions.py` — custom exceptions
- `backend/graph/adapters/` — adapter implementations
- `backend/tests/graph/` — existing tests (~50% coverage) to identify gaps

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use in-memory graph adapter for all tests — no external graph DB connections
- Test idempotency: upserting the same entity twice should not create duplicates
- Test error paths: missing entity → proper exception, invalid relationship → proper exception

## What NOT To Do
- Do NOT connect to a real graph database (Neo4j, etc.) in tests
- Do NOT duplicate tests that already exist and pass — identify gaps with `--cov-report=term-missing`
- Do NOT modify the graph service or adapter production code unless fixing a discovered bug
- Do NOT add test data that couples to a specific domain (use generic entity/relationship shapes)
- Do NOT skip error-path tests — they are the primary coverage gap

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=graph tests/graph/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
