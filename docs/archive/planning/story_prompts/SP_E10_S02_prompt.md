# Story E10-S02: Backend test coverage gap closure — LLM module

## Story
As a platform developer, I want ≥ 85% test coverage for the `llm/` module, so that the LLM service, adapters, and error paths are validated.

## Acceptance Criteria
1. `pytest --cov=llm tests/llm/` reports ≥ 85% line coverage.
2. Tests cover: happy-path completion, provider error → `LlmProviderError`, configuration error paths, token limit handling, in-memory adapter behavior.
3. Tests are isolated — no API calls to real LLM providers.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/tests/llm/test_service.py` — service-level tests
- `backend/tests/llm/test_adapters.py` — adapter tests (in-memory, any concrete adapters)
- `backend/tests/llm/test_models.py` — model validation tests
- `backend/tests/llm/conftest.py` — shared fixtures

## Reference Files to Read First
- `backend/llm/service.py` — LLM service implementation
- `backend/llm/protocols.py` — LLM protocol definitions
- `backend/llm/models.py` — domain models
- `backend/llm/exceptions.py` — custom exceptions
- `backend/llm/adapters/` — adapter implementations
- `backend/tests/llm/` — existing test files to review and expand

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All tests must be isolated — mock or use in-memory adapters, never call external LLM APIs
- Follow existing test patterns in other modules (e.g., `tests/graph/`, `tests/config/`)
- Use `pytest` fixtures for adapter setup, not global state

## What NOT To Do
- Do NOT make real API calls to OpenAI, Anthropic, or any external LLM provider
- Do NOT duplicate test logic already present — review existing tests first and fill gaps
- Do NOT add new production code unless needed to make existing code testable (e.g., missing `__init__.py`)
- Do NOT weaken type annotations to make tests pass — fix the test instead
- Do NOT skip or xfail tests to reach the coverage threshold

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=llm tests/llm/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
