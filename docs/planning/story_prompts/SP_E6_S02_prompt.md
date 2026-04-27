# Story E6-S02: Production ContextRetriever adapter — delegate to VectorStoreService

## Story
As a platform developer, I want a `ServiceContextRetriever` adapter that delegates `retrieve` to the `VectorStoreService`.

## Acceptance Criteria
1. `rag/adapters/vectorstore_bridge.py` implements `ContextRetrieverProtocol`.
2. Accepts `VectorStoreServiceProtocol`, converts query vector/filters into `VectorSearchRequest`, maps results to `RetrievedContextItem`.
3. Unit test with mock vectorstore service verifies mapping, score passthrough, metadata preservation.
4. Returns empty list (not error) when zero results.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P0      |
| Size         | S       |
| Dependencies | E3-S02  |

## Target Files
- `backend/rag/adapters/vectorstore_bridge.py` — new file implementing `ServiceContextRetriever`
- `backend/rag/adapters/__init__.py` — re-export `ServiceContextRetriever`
- `backend/tests/rag/test_vectorstore_bridge.py` — unit tests for the adapter

## Reference Files to Read First
- `backend/rag/protocols.py` — `ContextRetrieverProtocol` definition
- `backend/rag/adapters/in_memory.py` — existing in-memory adapter pattern to follow
- `backend/rag/adapters/protocols.py` — adapter-level protocol definitions
- `backend/rag/models.py` — `RetrievedContextItem` and related domain models
- `backend/rag/service_models.py` — RAG service request/response types
- `backend/vectorstore/protocols.py` — `VectorStoreServiceProtocol` (the dependency)
- `backend/vectorstore/service_models.py` — `VectorSearchRequest` and response types
- `backend/vectorstore/models.py` — vectorstore domain models

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The adapter must depend on `VectorStoreServiceProtocol` (abstract), never on a concrete vectorstore adapter
- Import `VectorStoreServiceProtocol` from `vectorstore.protocols` — allowed cross-module boundary via protocol dependency injection
- Map vectorstore results to `RetrievedContextItem` faithfully: preserve scores, metadata, and content
- Return empty list on zero results — never raise an error for "no results found"

## What NOT To Do
- Do NOT instantiate or import any concrete `VectorStoreService` implementation — accept the protocol via constructor injection
- Do NOT add new protocols or change `ContextRetrieverProtocol` — implement it as-is
- Do NOT add HTTP/network calls — this is a pure delegation adapter
- Do NOT modify `vectorstore/` module files
- Do NOT raise exceptions for zero search results — return an empty list
- Do NOT invent filter translation logic beyond what the existing types support

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Added `ServiceContextRetriever` in
`backend/rag/adapters/vectorstore_bridge.py` that satisfies
`ContextRetrieverProtocol` via constructor-injected `VectorServiceProtocol`
(the actual protocol name in `vectorstore.protocols`; the backlog text refers
to it as `VectorStoreServiceProtocol`). The adapter builds a
`VectorSearchRequest` from `knowledge_base_id`, `query_vector`, `limit`, and
`filters`, calls `service.search(...)`, and maps each `VectorSearchMatch` to
a `RetrievedContextItem` while preserving `record_id`, `content_id`, score,
content (substituting `""` when upstream content is `None` to satisfy
`RetrievedContextItem.content: str`), and a copied metadata dict. Returns an
empty list when no matches are found and never raises for empty results.
Re-exported via `rag.adapters.__init__`.

## Validation Note
From `backend/`:
`.venv/bin/pytest tests/rag/test_embeddings_bridge.py tests/rag/test_vectorstore_bridge.py -q`
→ 12 passed. `.venv/bin/ruff check` on the four touched files → All checks
passed. `.venv/bin/pyright` on the four touched files → 0 errors, 0 warnings.
