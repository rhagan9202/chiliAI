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
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
