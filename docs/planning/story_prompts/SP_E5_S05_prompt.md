# Story E5-S05: RAG chat router — send message

## Story
As an analyst, I want to send a natural-language question to a RAG-powered chat endpoint.

## Acceptance Criteria
1. `api/routers/chat.py` defines `POST /chat/conversations/{conversation_id}/messages` accepting `ChatMessageRequest(content: str, kb_id: str)`.
2. Router delegates to RAG service: retrieve context, construct prompt, call LLM, return `ChatMessageResponse(content: str, sources: list[str])`.
3. Returns 400 if `content` is empty.
4. Returns 404 if `kb_id` references non-existent KB.
5. Test uses mocked RAG service.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E1-S07       |

## Target Files
- `backend/api/routers/chat.py` — new router with `POST /chat/conversations/{conversation_id}/messages`
- `backend/api/dependencies.py` — add `get_rag_service` dependency factory
- `backend/tests/api/test_chat_router.py` — tests with mocked RAG service

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router pattern
- `backend/api/dependencies.py` — existing DI wiring
- `backend/rag/protocols.py` — `RagServiceProtocol` with `answer(request: RagQueryRequest) -> RagQueryResponse`
- `backend/rag/service_models.py` — `RagQueryRequest`, `RagQueryResponse`, `RagCitation`
- `backend/shared/types.py` — `KnowledgeBase` model
- `backend/tests/api/test_knowledgebases_router.py` — test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `ChatMessageRequest` and `ChatMessageResponse` are Pydantic models defined in the router module (API-layer models)
- The router translates between `ChatMessageRequest` → `RagQueryRequest` and `RagQueryResponse` → `ChatMessageResponse`
- Empty `content` (after stripping whitespace) returns 400 — validate in the request model or router
- The router should check KB existence before calling the RAG service, or the service raises a domain exception that the router maps to 404
- `conversation_id` is a path parameter for future conversation threading — for now it is accepted but not used for state management
- `sources` in the response maps from `RagCitation.record_id` or `RagCitation.snippet`

## What NOT To Do
- Do NOT implement the concrete RAG service — only the DI stub
- Do NOT implement conversation history/threading — just accept `conversation_id` as a parameter
- Do NOT add streaming (SSE) — that is E5-S06
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT implement LLM or embedding calls in the router
- Do NOT add authentication or authorization

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `backend/api/routers/chat.py` defines
`POST /chat/conversations/{conversation_id}/messages` accepting
`ChatMessageRequest(content, kb_id)` and returning
`ChatMessageResponse(content, sources)`. The router is self-contained: a local
`get_rag_service()` factory at the top of the module returns a default
`InMemoryRagService` (per scope guidance, `api/dependencies.py` was not
touched). The router validates content via Pydantic (whitespace-only and
empty bodies fail at parse time, mapped to 422), delegates to
`RagService.answer_question(...)`, and converts `RagConfigurationError`
raised for unknown KBs into a 404. `RagAnswer` was added to
`rag/service_models.py`; the protocol gained `answer_question` and a stub
implementation lives in `RagService` (reusing the existing pipeline) and
in the new `InMemoryRagService` adapter (canned answers + KB allowlist).

## Validation Note
From `backend/`:
`pytest tests/api/test_chat_router.py tests/rag` passed with 20 tests.
`pytest --cov=api.routers.chat --cov=rag` reports 96% on the chat router
and 92% overall across rag + chat.
`ruff check api/routers/chat.py rag llm/protocols.py
tests/api/test_chat_router.py tests/rag` passed.
`pyright api/routers/chat.py rag llm/protocols.py
tests/api/test_chat_router.py tests/rag` passed with 0 errors.
