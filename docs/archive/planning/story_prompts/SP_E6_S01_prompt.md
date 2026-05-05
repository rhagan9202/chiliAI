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
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Added `ServiceQueryEmbedder` in
`backend/rag/adapters/embeddings_bridge.py` that satisfies
`QueryEmbedderProtocol` via constructor-injected `EmbeddingsServiceProtocol`.
The adapter wraps the question in a single-item `EmbedRequest` (configurable
`model_name` and `content_id`), calls `service.embed(...)`, and returns the
first item's vector. `RagConfigurationError` is raised when the response has
no items, when the first item's vector is empty, or when the question is
blank. Re-exported via `rag.adapters.__init__`. Note the actual upstream
protocol method is `EmbeddingsServiceProtocol.embed(EmbedRequest)` — the
backlog wording referencing `embed_batch` was honored as "single-item batch
submission" through `EmbedRequest.submissions=[EmbedSubmission(...)]`.

## Validation Note
From `backend/`:
`.venv/bin/pytest tests/rag/test_embeddings_bridge.py tests/rag/test_vectorstore_bridge.py -q`
→ 12 passed. `.venv/bin/ruff check` on the four touched files → All checks
passed. `.venv/bin/pyright` on the four touched files → 0 errors, 0 warnings.
