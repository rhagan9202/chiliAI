# Story E17-S04: Shared utilities — json_serialize, retry decorator, truncate_text

## Story
As a platform developer, I want `shared/utils.py` to expose a Pydantic-aware JSON serializer, a reusable retry decorator with exponential backoff, and a safe text-truncation helper so these cross-cutting needs are not re-implemented in every service module.

## Acceptance Criteria
1. `shared/utils.py` adds:
   - `json_serialize(obj: object) -> str` — serializes any object to a JSON string; handles `datetime` (ISO format), Pydantic models (via `.model_dump()`), `UUID`, and `Enum` values; raises `TypeError` for unsupported types.
   - `retry(max_attempts: int = 3, backoff_factor: float = 1.0, retryable_exceptions: tuple[type[Exception], ...] = (Exception,)) -> Callable[[F], F]` — a decorator that retries the decorated function on specified exceptions with `backoff_factor * (2 ** attempt)` second delay between attempts; uses `time.sleep`.
   - `truncate_text(text: str, max_chars: int, *, suffix: str = "…") -> str` — truncates to `max_chars` characters at a word boundary when possible and appends `suffix`; returns the original string if it fits.
2. All three functions are exported from `shared/__init__.py`.
3. Unit tests cover: `json_serialize` with datetime/Pydantic/UUID/Enum/unsupported; `retry` succeeds on second attempt, fails after max_attempts; `truncate_text` at boundary, within limit, suffix appended.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P0       | S    | None         |

## Target Files
- `backend/shared/utils.py` — add `json_serialize`, `retry`, `truncate_text`
- `backend/shared/__init__.py` — export new utilities
- `backend/tests/shared/test_utils.py` — create/extend with tests for all three functions

## Reference Files to Read First
- `backend/shared/utils.py` — current `generate_id`, `normalize_text`, `utc_now`
- `backend/shared/__init__.py` — current exports
- `backend/tests/shared/test_utils.py` — existing utils tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- No new third-party dependencies — use `json`, `time`, `functools` from the standard library
- `retry` must preserve the wrapped function's `__name__`, `__doc__`, and type signature using `functools.wraps`
- `truncate_text` must not split a Unicode code point; use standard Python string slicing at character level
- `retry` uses `time.sleep` (blocking); async retry is not in scope

## What NOT To Do
- Do not add async variants of these utilities in this story
- Do not make `json_serialize` handle arbitrary Python objects — only the listed types
- Do not raise on `None` input to `json_serialize` — return `"null"`

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=shared tests/shared/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
