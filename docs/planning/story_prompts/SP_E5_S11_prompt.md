# Story E5-S11: Knowledge base router — create and list KBs

## Story
As an analyst, I want to create new knowledge bases and list existing ones.

## Acceptance Criteria
1. `POST /knowledgebases` accepts `CreateKbRequest(name: str, description: str)` returns KB with 201.
2. `GET /knowledgebases` returns `KbListResponse(items, total)` with limit/offset pagination.
3. KB creation generates unique ID and publishes `KnowledgeBaseCreatedEvent`.
4. Duplicate names allowed (IDs unique).
5. Tests: creation, listing, pagination.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | E1-S09       |

## Target Files
- `backend/api/routers/knowledgebases.py` — add `POST /knowledgebases` and `GET /knowledgebases` endpoints
- `backend/api/dependencies.py` — add `get_kb_service` dependency factory if needed
- `backend/tests/api/test_knowledgebases_router.py` — add tests for create, list, pagination

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router with `POST /{kb_id}/documents` endpoint
- `backend/api/dependencies.py` — existing DI wiring, event bus dependency
- `backend/shared/types.py` — `KnowledgeBase` model
- `backend/events/types.py` — existing `KnowledgeBaseCreatedEvent`
- `backend/events/protocols.py` — `EventBus` protocol for publishing events
- `backend/tests/api/test_knowledgebases_router.py` — existing tests for document upload

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `CreateKbRequest` is an API-layer Pydantic model: `name: str`, `description: str`
- `KbListResponse` is an API-layer Pydantic model: `items: list[KnowledgeBase]`, `total: int`
- KB creation must generate a unique ID (e.g., UUID4) and set `created_at` to UTC now
- KB creation publishes `KnowledgeBaseCreatedEvent` via the injected event bus
- `GET /knowledgebases` supports `limit` (default 50) and `offset` (default 0) query params
- The router needs a KB storage/service protocol — either extend the existing ingestion service or introduce a dedicated `KbServiceProtocol`
- Duplicate KB names are explicitly allowed per AC — only IDs must be unique
- Return 201 status code for successful creation

## What NOT To Do
- Do NOT implement the concrete KB storage backend — only protocol and DI stub
- Do NOT add update/patch KB endpoints — those are not in scope
- Do NOT add delete KB endpoint — that is E5-S12
- Do NOT break the existing `POST /{kb_id}/documents` endpoint
- Do NOT add authentication or authorization
- Do NOT enforce unique KB names — duplicates are allowed per AC

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
