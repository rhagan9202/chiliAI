# Story E18-S01: VectorStoreProtocol — delete, get_record, count, and batch_search

## Story
As a platform developer, I want the `VectorStoreProtocol` to include `delete()`, `get_record()`, `count()`, and `batch_search()` methods so that knowledge-base teardown, record retrieval for debugging, and high-throughput search are first-class supported operations.

## Acceptance Criteria
1. `vectorstore/protocols.py` adds to `VectorStoreProtocol`:
   - `delete(kb_id: str, record_id: str) -> None`
   - `get_record(kb_id: str, record_id: str) -> VectorRecord | None`
   - `count(kb_id: str) -> int`
   - `batch_search(requests: list[VectorSearchRequest]) -> list[VectorSearchResponse]`
2. The in-memory `InMemoryVectorStore` adapter in `vectorstore/adapters/in_memory.py` implements all four methods.
3. Existing tests pass; new unit tests cover all four methods including edge cases (delete non-existent, get missing record, batch of zero requests).

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/vectorstore/protocols.py` — add four new methods to protocol
- `backend/vectorstore/adapters/in_memory.py` — implement new methods
- `backend/tests/vectorstore/test_in_memory.py` — add tests for new methods

## Reference Files to Read First
- `backend/vectorstore/protocols.py` — current `VectorStoreProtocol`
- `backend/vectorstore/models.py` — `VectorRecord`, `VectorSearchRequest`, `VectorSearchResponse`, `VectorIndexRequest`, `VectorIndexReceipt`
- `backend/vectorstore/adapters/in_memory.py` — current implementation
- `backend/tests/vectorstore/` — existing vectorstore tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `delete` is a no-op when the record does not exist (do not raise)
- `get_record` returns `None` rather than raising when a record is not found
- `batch_search` returns an empty list for an empty input list — no error
- Method signatures must match the rest of the protocol's sync style (no async in this story)

## What NOT To Do
- Do not implement Qdrant or other production adapters here — that is E3-S01
- Do not add a `delete_kb(kb_id)` mass-delete method — that is E18-S02
- Do not change existing `index` or `search` method signatures

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=vectorstore tests/vectorstore/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
