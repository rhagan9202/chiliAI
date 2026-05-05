# Story E18-S02: VectorStoreService — KB delete flow, batch size limits, and audit persistence

## Story
As a platform developer, I want `VectorStoreService` to support a full knowledge-base teardown flow (delete all vectors for a KB), enforce batch size limits for large indexing submissions, and persist indexing receipts to object storage for audit and reproducibility.

## Acceptance Criteria
1. `vectorstore/service.py` adds `delete_knowledge_base(kb_id: str) -> int` that deletes all records for the given KB and returns the count deleted; publishes a `kb.vectors_deleted` event.
2. `index()` in `VectorStoreService` splits input `VectorIndexRequest` batches exceeding `max_batch_size` (configurable, default 500) into multiple adapter calls and aggregates receipts.
3. After successful indexing, the aggregated `VectorIndexReceipt` list is serialized to JSON and persisted to object store at `knowledgebases/{kb_id}/vector_index/{request_id}.json`.
4. Unit tests cover: `delete_knowledge_base` returns correct count and event published, batch splitting at boundary, object store persistence called with correct key.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E18-S01, E3-S08 |

## Target Files
- `backend/vectorstore/service.py` — add `delete_knowledge_base`, batch splitting, audit persistence
- `backend/vectorstore/models.py` — add `kb.vectors_deleted` event type if needed
- `backend/tests/vectorstore/test_service.py` — add delete and batch split tests

## Reference Files to Read First
- `backend/vectorstore/service.py` — current `VectorStoreService`
- `backend/vectorstore/protocols.py` — `VectorStoreProtocol` (post E18-S01)
- `backend/vectorstore/models.py` — vectorstore domain models
- `backend/storage/protocols.py` — `ObjectStore` protocol
- `backend/events/protocols.py` — `EventBus` for publishing events
- `backend/graph/service.py` — reference pattern for object store persistence and event publishing

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `delete_knowledge_base` must use `VectorStoreProtocol.delete()` in a loop — do not assume a mass-delete adapter method
- Batch splitting must not change the order of records in the aggregate receipts
- Persistence key must include the request/operation ID and not overwrite previous runs

## What NOT To Do
- Do not add `get_record` or `count` API endpoints here — those are separate stories
- Do not fail the entire index when object store persistence fails — log a warning and continue
- Do not implement the Qdrant-specific batch API — keep split logic at the service layer

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=vectorstore tests/vectorstore/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
