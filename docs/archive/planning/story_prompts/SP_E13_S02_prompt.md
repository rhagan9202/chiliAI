# Story E13-S02: LLM service hardening — retry, fallback model, and token budget

## Story
As a platform developer, I want `LLMService` to retry on transient provider errors with exponential backoff, fall back to a secondary model when the primary is unavailable, and enforce a pre-flight token budget check to prevent oversized requests.

## Acceptance Criteria
1. `llm/service.py` wraps `adapter.generate()` with retry logic: up to `max_attempts` (default 3) retries on `LLMProviderError`, with backoff `base_delay * (2 ** attempt)` seconds, capped at `max_delay` (default 30 s).
2. When a `fallback_adapter: LLMAdapterProtocol | None` is configured and all retries on the primary are exhausted, the service tries the fallback adapter once before raising.
3. If `request.max_tokens` is set and `adapter.count_tokens(request) > request.max_tokens`, raise `TokenBudgetExceededError` before calling `generate()`.
4. Retry parameters (`max_attempts`, `base_delay`, `max_delay`) are injectable via the `LLMService` constructor with the above defaults.
5. Tests cover: retry succeeds on third attempt, all retries exhausted invokes fallback, fallback also fails raises, token budget exceeded raises without calling generate.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E13-S01, E17-S04 |

## Target Files
- `backend/llm/service.py` — add retry loop, fallback adapter, token budget check
- `backend/llm/exceptions.py` — add `TokenBudgetExceededError`
- `backend/tests/llm/test_service.py` — add retry and fallback tests

## Reference Files to Read First
- `backend/llm/service.py` — current `LLMService`
- `backend/llm/exceptions.py` — existing exception hierarchy
- `backend/llm/adapters/protocols.py` — `LLMAdapterProtocol` (post E13-S01)
- `backend/shared/utils.py` — `retry` decorator (post E17-S04) if available, else implement inline
- `backend/tests/llm/test_service.py` — existing LLM service tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Retry uses `time.sleep` (blocking) in the first implementation — the worker is already in a thread; async retry is a future concern
- The `fallback_adapter` is optional; when absent, the service raises after exhausting retries
- `TokenBudgetExceededError` must be a subclass of the existing LLM exception base class

## What NOT To Do
- Do not add circuit-breaker logic here — that is E15-S01 at the RAG layer
- Do not implement model capability routing here (vision, tools) — future story
- Do not call `count_tokens` if `max_tokens` is not set — it is an optional guard

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=llm tests/llm/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
