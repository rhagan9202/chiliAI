# Story E3-S05: Anthropic LLM Adapter

## Story
As a platform developer, I want an LLM adapter calling the Anthropic Messages API, so that operators have a second LLM vendor option.

## Acceptance Criteria
1. `llm/adapters/anthropic_adapter.py` implements the LLM protocol.
2. API key is read from the configured environment variable.
3. Anthropic's `input_tokens` and `output_tokens` are mapped to `CompletionMetadata`.
4. Rate-limit handling with retry.
5. `anthropic` is listed as an optional dependency.
6. Unit test mocks the Anthropic client.

## Priority / Size / Dependencies
- **Priority:** P2
- **Size:** M
- **Dependencies:** E1-S06

## Target Files
- `backend/llm/adapters/anthropic_adapter.py` — **create** — Anthropic LLM adapter implementing the LLM protocol
- `backend/llm/adapters/__init__.py` — **modify** — re-export `AnthropicLlmClient`
- `backend/pyproject.toml` — **modify** — add `anthropic` as optional dependency under an extras group (e.g., `[anthropic]`)
- `backend/tests/llm/test_anthropic_adapter.py` — **create** — unit test with mocked Anthropic client

## Reference Files to Read First
- `backend/llm/protocols.py` — LLM protocol definition (the contract to implement)
- `backend/llm/models.py` — domain models (`GenerationRequest`, `GenerationResult`, `CompletionMetadata`, etc.)
- `backend/llm/service_models.py` — service request/response models
- `backend/llm/exceptions.py` — module-specific exceptions
- `backend/llm/adapters/in_memory.py` — reference implementation of the LLM protocol
- `backend/llm/adapters/openai_adapter.py` — sibling adapter for structural reference (if E3-S04 is complete)
- `backend/config/schema.py` — `LlmConfig` (api_key_env_var, model_name, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryLlmClient` structure and OpenAI adapter if available)
- Read the API key from `os.environ` using the env var name from `LlmConfig.api_key_env_var` — never hardcode keys
- Implement exponential backoff retry for rate-limit errors (max 3 attempts)
- Map Anthropic `usage.input_tokens` → `CompletionMetadata.prompt_tokens` and `usage.output_tokens` → `CompletionMetadata.completion_tokens`
- Support `claude-sonnet-4-20250514` and `claude-3-5-haiku-20241022` via config — do not hardcode model names
- The adapter must be usable without `anthropic` installed (optional import with clear error if missing)
- Anthropic Messages API requires `max_tokens` to be set explicitly — read from config or use a sensible default

## What NOT To Do
- Do not modify the LLM protocol — implement it as-is
- Do not add `anthropic` as a hard/required dependency — it must be optional
- Do not hardcode API keys or model names — read from config/environment
- Do not implement streaming in this story — non-streaming only
- Do not implement tool use or function calling — plain messages only
- Do not add custom HTTP client logic — use the official `anthropic` Python SDK
- Do not retry on non-rate-limit errors (e.g., 400, 401) — only retry rate limits

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=llm tests/llm/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
