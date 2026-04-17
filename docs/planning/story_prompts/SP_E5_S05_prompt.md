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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
