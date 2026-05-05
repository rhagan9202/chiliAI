# Story E15-S02: ContextRetriever protocol — min_score threshold, pagination, and hybrid search

## Story
As a platform developer, I want the `ContextRetrieverProtocol` to support a minimum similarity score threshold, cursor-based pagination, and a hybrid search mode (keyword + semantic) so retrieval quality and throughput can be tuned in production.

## Acceptance Criteria
1. `rag/adapters/protocols.py` extends `ContextRetrieverProtocol.retrieve()` with the following optional keyword parameters: `min_score: float | None = None`, `cursor: str | None = None`, `hybrid_weight: float | None = None` (0=pure keyword, 1=pure semantic, default `None` disables hybrid).
2. The call signature remains backward-compatible: existing callers that omit the new params must continue to work.
3. `rag/models.py` extends `RetrievedContextItem` with `score: float | None = None` and adds `next_cursor: str | None = None` to the relevant response container.
4. The in-memory `ContextRetriever` stub respects `min_score` (filters items below it) and ignores `cursor` and `hybrid_weight` (stubs return `next_cursor=None`).
5. Unit tests cover: `min_score` filtering, no filtering when `min_score=None`, cursor returned as `None` from in-memory stub.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/rag/adapters/protocols.py` — extend `ContextRetrieverProtocol.retrieve()` signature
- `backend/rag/models.py` — add `score` to `RetrievedContextItem`, `next_cursor` to response
- `backend/rag/adapters/in_memory.py` — update in-memory stub to respect `min_score`
- `backend/tests/rag/test_adapters.py` — add tests for the extended protocol

## Reference Files to Read First
- `backend/rag/adapters/protocols.py` — current `ContextRetrieverProtocol`
- `backend/rag/models.py` — current RAG domain models
- `backend/rag/adapters/in_memory.py` — in-memory adapter stubs
- `backend/tests/rag/` — existing RAG adapter tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Backward compatibility is mandatory — do not change the positional parameters
- `hybrid_weight` is a no-op in in-memory implementations; production Qdrant adapter (E3-S01) will implement it
- `min_score` must be in `[0.0, 1.0]` when provided; validate with `Field(ge=0.0, le=1.0)` or an assertion

## What NOT To Do
- Do not implement the Neo4j or Qdrant-backed retriever here — protocol extension only
- Do not change the reranker stage in this story
- Do not add `timeout_ms` — that is a follow-on story

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
