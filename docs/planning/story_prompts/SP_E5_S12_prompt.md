# Story E5-S12: Knowledge base router — get and delete KB

## Story
As an analyst, I want to retrieve a single KB by ID and delete a KB with all associated data.

## Acceptance Criteria
1. `GET /knowledgebases/{kb_id}` returns KB or 404.
2. `DELETE /knowledgebases/{kb_id}` removes KB metadata, all stored artifacts, returns 204.
3. Delete publishes `KnowledgeBaseDeletedEvent`.
4. 404 if not found.
5. Tests: get, delete, delete-nonexistent.

## Priority / Size / Dependencies
| Priority | Size | Dependencies     |
|----------|------|------------------|
| P1       | M    | E5-S11, E3-S08   |

## Target Files
- `backend/api/routers/knowledgebases.py` — add `GET /knowledgebases/{kb_id}` and `DELETE /knowledgebases/{kb_id}`
- `backend/events/types.py` — add `KnowledgeBaseDeletedEvent`
- `backend/tests/api/test_knowledgebases_router.py` — add tests for get, delete, 404 cases

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router with create/list from E5-S11
- `backend/api/dependencies.py` — existing DI wiring
- `backend/shared/types.py` — `KnowledgeBase` model
- `backend/events/types.py` — existing event types, `EventBase`, `KnowledgeBaseCreatedEvent`
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/storage/protocols.py` — `ObjectStore` protocol for artifact cleanup
- `backend/tests/api/test_knowledgebases_router.py` — existing tests from E5-S11

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `KnowledgeBaseDeletedEvent` extends `EventBase` with `knowledge_base_id: str`, `event_type: Literal["kb.delete"] = "kb.delete"`
- `DELETE` returns 204 No Content on success — use `status_code=status.HTTP_204_NO_CONTENT` with no response body
- `DELETE` returns 404 if the KB does not exist
- KB deletion must remove all associated stored artifacts (documents, parsed results, etc.) — delegate to the KB service
- The event should be published after successful deletion, not before
- `GET /knowledgebases/{kb_id}` returns the full `KnowledgeBase` model or 404

## What NOT To Do
- Do NOT implement cascade deletion logic in the router — delegate to service
- Do NOT implement soft-delete — use hard delete per the AC
- Do NOT break existing endpoints (create, list, document upload)
- Do NOT add update/patch endpoints
- Do NOT add authentication or authorization
- Do NOT delete from graph DB or vector store directly in the router — the service handles downstream cleanup

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
