# Story E6-S07: Citation formatting with source references

## Story
As an analyst, I want RAG responses to include structured citations linking answer claims to source documents and chunk offsets.

## Acceptance Criteria
1. `RagCitation` extended with `document_id: str | None`, `chunk_index: int | None`, `highlight: str | None`.
2. Citation builder maps `RetrievedContextItem.metadata` fields to citation fields.
3. Unit test verifies citation population when metadata present and graceful None when absent.
4. `RagQueryResponse.citations` ordered by descending relevance score.

## Priority / Size / Dependencies

| Field        | Value   |
|--------------|---------|
| Priority     | P2      |
| Size         | S       |
| Dependencies | None    |

## Target Files
- `backend/rag/models.py` — extend `RagCitation` with new fields
- `backend/rag/service.py` — add or update citation builder logic
- `backend/rag/service_models.py` — ensure `RagQueryResponse.citations` ordering
- `backend/tests/rag/test_models.py` — tests for extended `RagCitation`
- `backend/tests/rag/test_service.py` — tests for citation builder and ordering

## Reference Files to Read First
- `backend/rag/models.py` — current `RagCitation`, `RetrievedContextItem` definitions
- `backend/rag/service.py` — current citation handling in `RagService.answer()`
- `backend/rag/service_models.py` — `RagQueryResponse` definition
- `backend/rag/protocols.py` — protocol definitions for context
- `backend/tests/rag/test_models.py` — existing model tests
- `backend/tests/rag/test_service.py` — existing service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- New `RagCitation` fields must all be `Optional` (`str | None`, `int | None`) — citations from sources without metadata must not fail
- Citation builder should be a pure function or static method, testable in isolation
- Ordering by descending relevance score must be stable (preserve insertion order for equal scores)
- `RagCitation` must remain a frozen dataclass

## What NOT To Do
- Do NOT remove or rename existing `RagCitation` fields — only add new ones
- Do NOT make the new fields required — they must all be optional with `None` defaults
- Do NOT add citation extraction from LLM response text (NLP parsing) — citations come from retrieval metadata only
- Do NOT modify `RetrievedContextItem` — read its metadata as-is
- Do NOT break existing tests — extend them

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note (2026-04-26)

`RagCitation` (located in `rag/service_models.py` alongside the rest of the
public service-boundary models — not in `models.py` as the prompt suggested)
gained three optional fields: `document_id: str | None`, `chunk_index: int |
None`, `highlight: str | None`. Existing fields are unchanged.

Citation construction was extracted from inline list comprehensions into
two helpers in `rag/service.py`:

- `_citation_for(item)` reads `RetrievedContextItem.metadata` and pulls
  `document_id` (string), `chunk_index` (int, rejecting bool to avoid
  `True/False` becoming `1/0`), and `highlight` (string), falling back to
  the `text` metadata key for `highlight`. Missing or wrong-typed values
  resolve to `None`.
- `_build_citations(items)` orders citations by descending
  `RetrievedContextItem.score` with insertion-order stable tie-breaking, and
  is used by both `answer()` and the final `stream_answer()` chunk.

## Validation Note (2026-04-26)

```
.venv/bin/pytest tests/rag tests/api/test_chat_router.py tests/config -q   # 130 passed
.venv/bin/ruff check rag api/routers/chat.py config tests/rag tests/api/test_chat_router.py tests/config  # clean
.venv/bin/pyright rag api/routers/chat.py config tests/rag tests/api/test_chat_router.py tests/config     # 0 errors
.venv/bin/pytest tests/rag --cov=rag                                       # 95% line coverage
```
