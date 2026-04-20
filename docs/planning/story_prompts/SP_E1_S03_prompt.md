# Story E1-S03: Consolidate `_utc_now()` into `shared/utils.py`

## Story
As a platform developer, I want a single `utc_now()` function in `shared/utils.py` replacing the duplicated `_utc_now()` definitions across 9+ modules, so that timestamp generation has one canonical source and can be patched in a single place during tests.

## Acceptance Criteria
1. `shared/utils.py` exports `utc_now() -> datetime` returning `datetime.now(timezone.utc)`.
2. Every module-local `_utc_now()` (events/types.py, graph/models.py, graph/service_models.py, vectorstore/models.py, vectorstore/service_models.py, llm/models.py, agent/models.py, ingestion/service_models.py, embeddings/models.py, monitoring/models.py, ingestion/chunker.py) is replaced with an import from `shared.utils`.
3. All existing tests pass without changes to assertions.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | None         |

## Target Files
- `backend/shared/utils.py` — add `utc_now()` function, update `__all__`
- `backend/events/types.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/graph/models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/graph/service_models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/vectorstore/models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/vectorstore/service_models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/llm/models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/agent/models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/ingestion/service_models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/embeddings/models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/monitoring/models.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/ingestion/chunker.py` — remove local `_utc_now()`, import from `shared.utils`
- `backend/tests/shared/test_utils.py` — add tests for `utc_now()`

## Reference Files to Read First
- `backend/shared/utils.py` — current utility functions and `__all__` exports
- `backend/events/types.py` — example of current `_utc_now()` pattern and usage in `Field(default_factory=_utc_now)`
- `backend/tests/shared/test_utils.py` — existing test patterns for shared utils
- Each of the 11 target modules above — verify `_utc_now()` definition and all call sites before replacing

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- This is a mechanical refactor — each module replacement is: (a) delete the local `def _utc_now()` function, (b) add `from shared.utils import utc_now`, (c) update all `default_factory=_utc_now` references to `default_factory=utc_now`
- Remove the TODO comment in `shared/utils.py` about `utc_now()` since it will be implemented
- The function must be public (`utc_now`, not `_utc_now`) since it's now a shared API
- Grep for `_utc_now` across the entire backend to ensure no occurrences are missed

## What NOT To Do
- Do NOT change any function signatures, model field names, or default behaviors
- Do NOT modify test assertions — all existing tests must pass as-is
- Do NOT add any new model fields or types — this is purely a refactor
- Do NOT touch files that don't contain `_utc_now()`
- Do NOT add retry logic, JSON serializers, or other TODO items from `shared/utils.py` — those are separate stories
- Do NOT change `datetime.now(timezone.utc)` to any other timestamp implementation

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=shared tests/shared/` >= 85% coverage for affected module
- [x] `grep -r "_utc_now" backend/ --include="*.py"` returns zero results (excluding `__pycache__`)
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
