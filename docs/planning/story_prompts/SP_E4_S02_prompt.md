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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
