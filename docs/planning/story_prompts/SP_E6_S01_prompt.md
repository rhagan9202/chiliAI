# Story E6-S01: Production QueryEmbedder adapter — delegate to EmbeddingsService

## Story
As a platform developer, I want a `ServiceQueryEmbedder` adapter that delegates `embed_query` to the `EmbeddingsService`, so that RAG queries use the same embedding model as ingestion.

## Acceptance Criteria
1. `rag/adapters/embeddings_bridge.py` implements `QueryEmbedderProtocol`.
2. Accepts `EmbeddingsServiceProtocol` dependency, calls `embed_batch` with single-item list, returns vector.
3. Unit test confirms forwarding and correct vector return.
4. Raises `RagConfigurationError` if embeddings service returns empty result.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P0      |
| Size         | S       |
| Dependencies | E3-S04  |

## Target Files
- `backend/rag/adapters/embeddings_bridge.py` — new file implementing `ServiceQueryEmbedder`
- `backend/rag/adapters/__init__.py` — re-export `ServiceQueryEmbedder`
- `backend/tests/rag/test_embeddings_bridge.py` — unit tests for the adapter

## Reference Files to Read First
- `backend/rag/protocols.py` — `QueryEmbedderProtocol` definition
- `backend/rag/adapters/in_memory.py` — existing in-memory adapter pattern to follow
- `backend/rag/adapters/protocols.py` — adapter-level protocol definitions
- `backend/rag/exceptions.py` — `RagConfigurationError` definition
- `backend/rag/models.py` — RAG domain models
- `backend/embeddings/protocols.py` — `EmbeddingsServiceProtocol` (the dependency)
- `backend/embeddings/service_models.py` — request/response types for embeddings service

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The adapter must depend on the `EmbeddingsServiceProtocol` (abstract), never on a concrete embeddings adapter
- Import `EmbeddingsServiceProtocol` from `embeddings.protocols` — this is the allowed cross-module boundary via protocol dependency injection
- Raise `RagConfigurationError` (from `rag.exceptions`) on empty results, not a generic exception

## What NOT To Do
- Do NOT instantiate or import any concrete `EmbeddingsService` implementation — accept the protocol via constructor injection
- Do NOT add new protocols or change `QueryEmbedderProtocol` — implement it as-is
- Do NOT add HTTP/network calls — this is a pure delegation adapter
- Do NOT modify `embeddings/` module files
- Do NOT add optional dependencies or feature flags beyond what the AC requires

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
