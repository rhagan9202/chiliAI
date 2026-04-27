# Story E5-S13: Knowledge base router — list and delete documents within a KB

## Story
As an analyst, I want to list documents in a KB and delete individual documents.

## Acceptance Criteria
1. `GET /knowledgebases/{kb_id}/documents` returns `DocumentListResponse(items, total)` with pagination.
2. `DocumentSummary`: id, filename, content_type, size_bytes, status, created_at.
3. `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` removes doc and artifacts, returns 204.
4. 404 if KB or doc not found.
5. Tests: listing and deletion.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | E5-S11       |

## Target Files
- `backend/api/routers/knowledgebases.py` — add `GET /knowledgebases/{kb_id}/documents` and `DELETE /knowledgebases/{kb_id}/documents/{doc_id}`
- `backend/tests/api/test_knowledgebases_router.py` — add document listing and deletion tests

## Reference Files to Read First
- `backend/api/routers/knowledgebases.py` — existing router with KB endpoints and `POST /{kb_id}/documents`
- `backend/api/dependencies.py` — existing DI wiring
- `backend/ingestion/service_models.py` — `DocumentReceipt`, `DocumentSubmission` for document model patterns
- `backend/ingestion/models.py` — ingestion-layer document models
- `backend/storage/protocols.py` — `ObjectStore` protocol
- `backend/shared/types.py` — for reference types
- `backend/tests/api/test_knowledgebases_router.py` — existing tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `DocumentListResponse` is an API-layer Pydantic model: `items: list[DocumentSummary]`, `total: int`
- `DocumentSummary` is an API-layer Pydantic model: `id: str`, `filename: str`, `content_type: str | None`, `size_bytes: int | None`, `status: str`, `created_at: datetime`
- `GET /knowledgebases/{kb_id}/documents` supports `limit` (default 50) and `offset` (default 0) query params
- Both endpoints return 404 if `kb_id` does not reference an existing KB
- `DELETE` returns 404 if `doc_id` is not found within the specified KB
- `DELETE` returns 204 No Content on success — no response body
- Document deletion removes the document and all derived artifacts (parsed content, embeddings, etc.) — delegate to service

## What NOT To Do
- Do NOT implement document storage or retrieval logic in the router
- Do NOT break the existing `POST /{kb_id}/documents` upload endpoint
- Do NOT add document update/patch endpoints
- Do NOT add document content download endpoint — that is out of scope
- Do NOT add authentication or authorization
- Do NOT implement cascade cleanup in the router — delegate to service

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Added
`GET /knowledgebases/{kb_id}/documents` and
`DELETE /knowledgebases/{kb_id}/documents/{document_id}` to
`backend/api/routers/knowledgebases.py`. The list endpoint returns
`DocumentListResponse(items, total)` paginated by `limit`/`offset`; each
`DocumentSummary` carries `id`, `filename`, `content_type`, `size_bytes`,
`status`, and `created_at`. Document metadata is recorded in the repository
during the existing `POST /{kb_id}/documents` upload path (when a KB exists
in the metadata store) so the list endpoint has data to project. The DELETE
endpoint cleans every object-store key prefixed
`knowledgebases/{kb_id}/documents/{document_id}/` and removes the document
record. Both endpoints return 404 when the KB is missing; DELETE additionally
returns 404 when the document id is absent.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/api/test_knowledgebases_router.py
tests/events tests/storage -q` passes (121 tests). `.venv/bin/ruff check api
events tests/api/test_knowledgebases_router.py tests/events` clean.
`.venv/bin/pyright` on the touched files returns 0 errors. Tests cover paged
listing, summary fields populated from upload metadata, deletion of a
document with cascading object-store cleanup, and 404 on both missing KB and
missing document.
