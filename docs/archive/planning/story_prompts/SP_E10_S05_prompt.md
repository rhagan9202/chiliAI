# Story E10-S05: Backend test coverage gap closure — storage module

## Story
As a platform developer, I want ≥ 85% test coverage for the `storage/` module, so that object store operations and adapter behavior are validated.

## Acceptance Criteria
1. `pytest --cov=storage tests/storage/` reports ≥ 85% line coverage.
2. Tests cover: put_bytes, get_bytes, delete, list_keys, key-not-found error, empty content handling, metadata round-trip.
3. Tests cover both in-memory and local-filesystem adapters (if the local adapter exists by this point).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/tests/storage/test_adapters.py` — adapter tests (in-memory, local filesystem)
- `backend/tests/storage/test_models.py` — model validation tests
- `backend/tests/storage/conftest.py` — shared fixtures

## Reference Files to Read First
- `backend/storage/protocols.py` — storage protocol definitions
- `backend/storage/models.py` — storage domain models
- `backend/storage/adapters/` — adapter implementations
- `backend/tests/storage/` — existing tests (~70% coverage) to identify gaps

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Use `tmp_path` fixture for local filesystem adapter tests — no writing to source tree
- Test edge cases: empty bytes, very large keys, special characters in keys
- In-memory adapter tests must be deterministic and isolated between test functions

## What NOT To Do
- Do NOT connect to real object stores (S3, GCS, etc.) in tests
- Do NOT create files outside `tmp_path` in filesystem adapter tests
- Do NOT test with actual large blobs (> 1 MB) — use small payloads that exercise the same code paths
- Do NOT skip metadata round-trip tests — verify metadata is stored and retrieved correctly
- Do NOT modify production code to inflate coverage

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=storage tests/storage/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
