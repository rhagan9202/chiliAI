# Story E5-S06: RAG chat router — streaming response via SSE

## Story
As an analyst, I want the RAG chat response to stream token-by-token via Server-Sent Events.

## Acceptance Criteria
1. `POST /chat/conversations/{conversation_id}/messages?stream=true` returns `StreamingResponse` with `text/event-stream`.
2. Each SSE event: `{"token": "...", "done": false}`.
3. Final event: `{"token": "", "done": true, "sources": [...]}`.
4. LLM adapter protocol defines optional `generate_stream()`.
5. Test verifies SSE format and token concatenation.

## Priority / Size / Dependencies
| Priority | Size | Dependencies     |
|----------|------|------------------|
| P2       | M    | E5-S05, E3-S04   |

## Target Files
- `backend/api/routers/chat.py` — modify `POST /chat/conversations/{conversation_id}/messages` to support `stream=true` query param
- `backend/rag/protocols.py` — extend `RagServiceProtocol` with `stream_answer` method returning an async iterator
- `backend/rag/service_models.py` — add `RagStreamChunk` model
- `backend/llm/protocols.py` — extend `LlmServiceProtocol` with optional `generate_stream()` method
- `backend/tests/api/test_chat_router.py` — add SSE streaming tests

## Reference Files to Read First
- `backend/api/routers/chat.py` — the chat router from E5-S05
- `backend/rag/protocols.py` — existing `RagServiceProtocol` with `answer` method
- `backend/rag/service_models.py` — `RagQueryRequest`, `RagQueryResponse`, `RagCitation`
- `backend/llm/protocols.py` — existing `LlmServiceProtocol`
- `backend/llm/service_models.py` — existing LLM service models
- `backend/tests/api/test_chat_router.py` — existing chat tests from E5-S05

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- Use `fastapi.responses.StreamingResponse` with `media_type="text/event-stream"`
- SSE format: each event is `data: {json}\n\n` — use standard SSE framing
- `RagStreamChunk` model: `token: str`, `done: bool`, `sources: list[str] | None = None`
- The `stream_answer` protocol method returns `AsyncIterator[RagStreamChunk]` or `collections.abc.AsyncIterator`
- When `stream=false` (default), behavior is unchanged from E5-S05
- The router async-iterates over chunks from the service and yields SSE-formatted lines
- Handle client disconnect gracefully — if the client closes the connection, stop iteration

## What NOT To Do
- Do NOT implement the concrete streaming LLM adapter — only the protocol extension
- Do NOT implement WebSocket streaming — use SSE only per the AC
- Do NOT add conversation history management
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT add authentication or authorization
- Do NOT break the non-streaming path from E5-S05

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `POST /chat/conversations/{id}/messages?stream=true`
returns a `StreamingResponse` with `media_type="text/event-stream"`. Each event
is `data: {json}\n\n` carrying `{token, done}`; the terminal event is
`{token: "", done: true, sources: [...]}`. Errors raised by the rag service
during streaming are emitted as a single `{error, done: true}` event so the
HTTP status remains 200 (SSE-style error reporting). `RagStreamChunk` was added
to `rag/service_models.py`; `RagServiceProtocol.stream_answer` returns
`AsyncIterator[RagStreamChunk]` and is implemented as an async generator on
`RagService` (token-splits the canned answer for now) and on
`InMemoryRagService`. `LlmServiceProtocol` gained an optional
`generate_stream(request) -> AsyncIterator[str]` whose default body raises
`NotImplementedError`, leaving concrete streaming adapters for Epic 6.

## Validation Note
From `backend/`:
`pytest tests/api/test_chat_router.py tests/rag` passed with 20 tests
(including dedicated SSE format / done-sentinel / unknown-KB streaming cases).
`ruff check api/routers/chat.py rag llm/protocols.py
tests/api/test_chat_router.py tests/rag` passed.
`pyright api/routers/chat.py rag llm/protocols.py
tests/api/test_chat_router.py tests/rag` passed with 0 errors.
