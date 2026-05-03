# Story E15-S01: RAG service hardening — retry, circuit breaker, and graceful degradation

## Story
As a platform developer, I want `RAGService` to retry transient retrieval and generation failures with backoff, open a circuit breaker on repeated LLM failures, and degrade gracefully (return context-only answer) when graph expansion fails.

## Acceptance Criteria
1. `rag/service.py` wraps `context_retriever.retrieve()` with up to 2 retries on `VectorStoreError` with 0.5 s backoff.
2. LLM generation errors exceeding a configurable `circuit_breaker_threshold` (default 5 consecutive failures) cause the circuit to open; subsequent calls raise `RagCircuitOpenError` immediately without calling the LLM.
3. When `graph_expander.expand()` raises any exception, the service logs a warning and continues with the retrieved context alone (graceful degradation, not a full failure).
4. `rag/exceptions.py` adds `RagCircuitOpenError`.
5. Circuit state is reset after `circuit_reset_seconds` (default 60 s) without a call.
6. Tests cover: retrieval retry succeeds, circuit opens after threshold, circuit resets, graph expansion failure degrades gracefully.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E17-S04      |

## Target Files
- `backend/rag/service.py` — add retry, circuit breaker, and degradation logic
- `backend/rag/exceptions.py` — add `RagCircuitOpenError`
- `backend/tests/rag/test_service.py` — add hardening tests

## Reference Files to Read First
- `backend/rag/service.py` — current `RAGService`
- `backend/rag/exceptions.py` — existing RAG exception hierarchy
- `backend/rag/protocols.py` — `ContextRetrieverProtocol`, `GraphContextExpanderProtocol`, `AnswerGeneratorProtocol`
- `backend/shared/utils.py` — shared retry utility (post E17-S04) if available
- `backend/tests/rag/test_service.py` — existing RAG service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Circuit breaker is in-process, not distributed — acceptable for single-worker deployments
- Circuit state is per `RAGService` instance — not a global
- Graceful degradation must be visible in `RagAnswer.metadata` (add `"graph_expansion": "skipped"`)

## What NOT To Do
- Do not implement streaming response here — that is E6-S06
- Do not add request caching/memoization here — future story
- Do not apply the circuit breaker to retrieval — only to LLM generation

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
