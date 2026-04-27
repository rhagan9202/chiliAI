# Story E4-S01: Wire embeddings step after graph.updated

## Story
As a platform developer, I want the worker coordinator to consume `graph.updated` events, generate embeddings for upserted entities, and publish an `embeddings.complete` event.

## Acceptance Criteria
1. `agent/coordinator.py` registers a handler for `GraphUpdatedEvent`.
2. The handler loads the graph update artifact from object storage, retrieves entity texts, calls the embeddings service, and persists `EmbeddingResult` to object storage.
3. An `EmbeddingsCompleteEvent` is published with the embeddings storage key and entity count.
4. `events/types.py` defines `EmbeddingsCompleteEvent` with appropriate reference model.
5. Unit test verifies the handler chains correctly with in-memory adapters.
6. `correlation_id` is propagated from the incoming event.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P0          |
| Size         | M           |
| Dependencies | E1-S08      |

## Target Files
- `backend/agent/coordinator.py` — add `GraphUpdatedEvent` handler, embeddings generation step
- `backend/events/types.py` — define `EmbeddingsCompleteEvent`
- `backend/tests/agent/test_coordinator.py` — unit tests for the new handler

## Reference Files to Read First
- `backend/agent/coordinator.py` — current coordinator structure and existing handlers
- `backend/agent/protocols.py` — worker protocol definitions
- `backend/events/types.py` — existing event type definitions and `EventBase` pattern
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/embeddings/service.py` — embeddings service interface
- `backend/embeddings/protocols.py` — `EmbeddingsProtocol`
- `backend/storage/protocols.py` — object storage protocol for artifact retrieval/persistence
- `backend/graph/models.py` — graph entity models for extracting text
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The coordinator is the only module allowed to orchestrate across embeddings, graph, and storage
- `correlation_id` must be threaded from incoming `GraphUpdatedEvent` into the published `EmbeddingsCompleteEvent`
- Use the object storage protocol to load/persist artifacts — do not couple to a specific storage backend
- `EmbeddingsCompleteEvent` must follow the same `EventBase` pattern as existing event types

## What NOT To Do
- Do not import embeddings internals directly — use the protocol/service interface
- Do not hardcode storage keys or paths; derive them from the incoming event's artifact references
- Do not add REST endpoints — this is worker-only logic
- Do not modify the embeddings service itself; only call it
- Do not skip `correlation_id` propagation
- Do not introduce new dependencies or adapters not already in the codebase

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 25, 2026. The worker now handles `graph.updated` by
loading the persisted graph update and validation artifacts, selecting
upserted entities in deterministic ID order, generating stable entity text,
calling the embeddings service boundary, storing an `EmbeddingResult` artifact
under a key derived from the graph update artifact key, and publishing
`embeddings.complete` with propagated `correlation_id`.

## Validation Note
From `backend/`: `pytest tests/agent/ --cov=agent --cov-report=term-missing`
passed with 17 tests and 89% agent coverage. `ruff check agent events
tests/agent` passed. `pyright agent events tests/agent` passed with 0 errors.
