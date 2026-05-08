# Story E6-S06: Streaming RAG response support

## Story
As a platform developer, I want `RagService` to support streaming answer generation via an iterator-based protocol method.

## Acceptance Criteria
1. `AnswerGeneratorProtocol` gains `stream_generate(request) -> Iterator[str]`.
2. `RagServiceProtocol` gains `stream_answer(request) -> Iterator[RagStreamChunk]`.
3. `RagStreamChunk`: `chunk_text: str`, `is_final: bool`, optional `citations: list[RagCitation]` (only on final).
4. `InMemoryAnswerGenerator` implements `stream_generate` by yielding full answer in one chunk.
5. `RagService.stream_answer()` embeds query, retrieves context, delegates to `stream_generate`, wraps in `RagStreamChunk`.
6. Unit test verifies streaming pipeline end-to-end with in-memory adapter.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P1      |
| Size         | M       |
| Dependencies | E6-S04  |

## Target Files
- `backend/rag/models.py` — add `RagStreamChunk` dataclass
- `backend/rag/protocols.py` — add `stream_generate` to `AnswerGeneratorProtocol`, add `stream_answer` to `RagServiceProtocol`
- `backend/rag/service.py` — implement `RagService.stream_answer()`
- `backend/rag/adapters/in_memory.py` — add `stream_generate` to `InMemoryAnswerGenerator`
- `backend/rag/adapters/__init__.py` — update exports if needed
- `backend/tests/rag/test_service.py` — add streaming pipeline tests
- `backend/tests/rag/test_in_memory_adapter.py` — add `stream_generate` tests

## Reference Files to Read First
- `backend/rag/protocols.py` — current `AnswerGeneratorProtocol` and `RagServiceProtocol`
- `backend/rag/models.py` — existing `RagCitation` and related models
- `backend/rag/service.py` — current `RagService.answer()` implementation (streaming mirrors this flow)
- `backend/rag/service_models.py` — `RagGenerationRequest` and related types
- `backend/rag/adapters/in_memory.py` — existing `InMemoryAnswerGenerator` to extend
- `backend/tests/rag/test_service.py` — existing service tests for pattern reference
- `backend/tests/rag/test_in_memory_adapter.py` — existing adapter tests for pattern reference

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use `collections.abc.Iterator[str]` for `stream_generate` return type — not `Generator` or `AsyncIterator`
- Use `collections.abc.Iterator[RagStreamChunk]` for `stream_answer` return type
- `RagStreamChunk` must be a frozen dataclass consistent with other models in `models.py`
- `citations` on `RagStreamChunk` should only be populated on the final chunk (`is_final=True`)
- The streaming pipeline must perform embedding + retrieval before streaming begins (not lazily)

## What NOT To Do
- Do NOT use async iterators (`AsyncIterator`) — keep synchronous to match existing patterns
- Do NOT add WebSocket or SSE transport concerns — this story is about the service-layer iterator, not the HTTP layer
- Do NOT break existing `answer()` method or its tests — `stream_answer()` is additive
- Do NOT add new dependencies for streaming support
- Do NOT change the signature of existing protocol methods — only add new ones
- Do NOT stream the embedding or retrieval phases — only the generation phase streams

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note (2026-04-26)

E5-S06 reconciliation: the previously stubbed `RagStreamChunk(token, done,
sources)` (in `service_models.py`) and async `stream_answer(*,
knowledge_base_id, question)` were replaced with the E6-S06 production
shape:

- `RagStreamChunk(chunk_text: str, is_final: bool, citations: list[RagCitation])`
  remains in `service_models.py` (where `RagCitation` already lives, instead
  of the prompt-suggested `models.py` — both are co-located in this module).
- `AnswerGeneratorProtocol.stream_generate(request) -> Iterator[str]` added.
- `RagServiceProtocol.stream_answer(request: RagQueryRequest) -> Iterator[RagStreamChunk]`
  is now sync (the prompt's stated rationale was that
  `LlmServiceProtocol.generate_stream` is sync — it is actually `AsyncIterator`,
  but sync was kept anyway because the prompt explicitly required it and the
  production bridge wraps a single-shot generation as one chunk for now).
- `InMemoryAnswerGenerator.stream_generate` yields the full canned answer in
  one chunk; `RagService.stream_answer` runs `_prepare_state` →
  `_expand_graph_context` → `_build_generation_request` → `stream_generate`,
  wraps each chunk as `is_final=False`, then emits a final
  `is_final=True` chunk with full citations.
- Chat router (`api/routers/chat.py`) was updated: SSE wire format is
  unchanged (`data: {"token": "...", "done": false}\n\n`), but the router
  now drives the sync iterator inside an `async def` SSE generator and maps
  `chunk.chunk_text → token`, `chunk.is_final → done`,
  `chunk.citations[*].record_id → sources` on the final chunk.
- `InMemoryRagService` (the chat-router fixture stub) updated to match the
  new sync-iterator + new chunk shape.

## Validation Note (2026-04-26)

```
.venv/bin/pytest tests/rag tests/api/test_chat_router.py tests/config -q   # 130 passed
.venv/bin/ruff check rag api/routers/chat.py config tests/rag tests/api/test_chat_router.py tests/config  # clean
.venv/bin/pyright rag api/routers/chat.py config tests/rag tests/api/test_chat_router.py tests/config     # 0 errors
.venv/bin/pytest -q                                                        # 692 passed, 3 skipped
```
