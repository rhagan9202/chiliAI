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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
