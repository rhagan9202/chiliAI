# Story E4-S02: Wire vector indexing step after embeddings.complete

## Story
As a platform developer, I want the worker coordinator to consume `embeddings.complete` events, upsert vectors into the vector store, and publish a `vectors.indexed` event.

## Acceptance Criteria
1. `agent/coordinator.py` registers a handler for `EmbeddingsCompleteEvent`.
2. The handler loads `EmbeddingResult` from storage, constructs `VectorRecord` instances with entity metadata, and calls `VectorStoreProtocol.upsert_records`.
3. A `VectorsIndexedEvent` is published upon success.
4. `events/types.py` defines `VectorsIndexedEvent`.
5. Unit test verifies the handler with in-memory vector store and embedder.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P0          |
| Size         | M           |
| Dependencies | E4-S01      |

## Target Files
- `backend/agent/coordinator.py` — add `EmbeddingsCompleteEvent` handler, vector upsert step
- `backend/events/types.py` — define `VectorsIndexedEvent`
- `backend/tests/agent/test_coordinator.py` — unit tests for the new handler

## Reference Files to Read First
- `backend/agent/coordinator.py` — current coordinator structure and existing handlers (including E4-S01 handler)
- `backend/events/types.py` — existing event types including `EmbeddingsCompleteEvent`
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/vectorstore/protocols.py` — `VectorStoreProtocol` and `upsert_records` signature
- `backend/vectorstore/models.py` — `VectorRecord` definition
- `backend/embeddings/models.py` — `EmbeddingResult` model
- `backend/storage/protocols.py` — object storage protocol for loading artifacts
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The coordinator is the only module allowed to wire vectorstore and embeddings together
- Construct `VectorRecord` instances with meaningful entity metadata (IDs, labels, etc.)
- `correlation_id` must be propagated from the incoming `EmbeddingsCompleteEvent` to `VectorsIndexedEvent`
- Use the object storage protocol to load `EmbeddingResult` — do not couple to a specific backend

## What NOT To Do
- Do not modify the vector store service or protocol — only call it
- Do not modify the embeddings service — only load its output from storage
- Do not add REST endpoints — this is worker-only logic
- Do not hardcode vector dimensions or collection names
- Do not skip entity metadata when constructing `VectorRecord` instances
- Do not introduce new dependencies not already in the codebase

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `handle_embeddings_complete` is now registered
in `handle_event` for `EmbeddingsCompleteEvent`. The handler loads the
persisted `EmbeddingResult` artifact from the object store, resolves the
companion `ValidationReport` to enrich `entity_type` metadata, constructs
`VectorRecord` instances keyed `<knowledge_base_id>:<entity_id>` with
`knowledge_base_id`, `entity_id`, `entity_type`, and the source artifact
identifiers, and calls `VectorStoreProtocol.upsert_records`. A new
`VectorsIndexedDocumentReference` model attaches per-document totals
(`vector_count`, `record_ids`, `embeddings_storage_key`) to the existing
`VectorsIndexedEvent`. The published event propagates the incoming
`correlation_id` so downstream consumers stay correlated.

## Validation Note
From `backend/`: `pytest tests/agent tests/events tests/api --cov=agent
--cov=events --cov=api --cov-report=term-missing` passed with 91 tests; agent
coverage 87%. `ruff check agent events api tests/agent tests/events
tests/api` passed. `pyright agent events api tests/agent tests/events
tests/api` reported 0 errors.
