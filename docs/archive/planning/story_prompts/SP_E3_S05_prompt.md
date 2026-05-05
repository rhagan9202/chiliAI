# Story E3-S05: Anthropic LLM Adapter

**Status:** Complete on April 25, 2026.

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
- `backend/llm/__init__.py` — **modify** — re-export `AnthropicLlmClient`
- `backend/pyproject.toml` — **modify** — add `anthropic` as optional dependency under an extras group (e.g., `[anthropic]`)
- `backend/tests/llm/test_anthropic_adapter.py` — **create** — unit test with mocked Anthropic client

## Reference Files to Read First
- `backend/llm/adapters/protocols.py` — LLM adapter protocol definition (the contract to implement)
- `backend/llm/protocols.py` — service-level LLM protocol boundary
- `backend/llm/models.py` — domain models (`GenerationRequest`, `GenerationResult`, `CompletionMetadata`, etc.)
- `backend/llm/service_models.py` — service request/response models
- `backend/llm/exceptions.py` — module-specific exceptions
- `backend/llm/adapters/in_memory.py` — reference implementation of the LLM protocol
- `backend/llm/adapters/openai_adapter.py` — sibling adapter for structural reference (if E3-S04 is complete)
- `backend/config/schema.py` — `LlmConfig` (api_key_env_var, model, temperature, max_tokens, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryLlmClient` structure and OpenAI adapter if available)
- Read the API key from `os.environ` using the env var name from `LlmConfig.api_key_env_var` — never hardcode keys
- Implement exponential backoff retry for rate-limit errors (max 3 total attempts, sleeping 1s then 2s before the final attempt)
- Map Anthropic `usage.input_tokens` → `CompletionMetadata.prompt_tokens` and `usage.output_tokens` → `CompletionMetadata.completion_tokens`
- Support `claude-sonnet-4-20250514` and `claude-3-5-haiku-20241022` via config — do not hardcode model names
- The adapter must be usable without `anthropic` installed (optional import with clear error if missing)
- Anthropic Messages API requires `max_tokens` to be set explicitly — read from config or use a sensible default
- Map normalized `MessageRole.SYSTEM` messages to Anthropic's top-level `system` parameter; do not send `system` as a message role.
- This story does not wire provider selection into API dependencies or the agent coordinator; that remains a separate production-wiring story.

## What NOT To Do
- Do not modify the LLM protocol — implement it as-is
- Do not add `anthropic` as a hard/required dependency — it must be optional
- Do not hardcode API keys or model names — read from config/environment
- Do not implement streaming in this story — non-streaming only
- Do not implement tool use or function calling — plain messages only
- Do not add custom HTTP client logic — use the official `anthropic` Python SDK
- Do not retry on non-rate-limit errors (e.g., 400, 401) — only retry rate limits

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=llm tests/llm/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
- Added `backend/llm/adapters/anthropic_adapter.py` implementing `LlmClientProtocol` with lazy Anthropic SDK import, environment-driven API key lookup via `LlmConfig.api_key_env_var`, system-message extraction into Anthropic's top-level `system` field, response text-block concatenation, optional usage-token mapping, and 429-only exponential backoff retry.
- Re-exported `AnthropicLlmClient` from `backend/llm/adapters/__init__.py` and `backend/llm/__init__.py` without changing provider-selection wiring.
- Added the optional `anthropic` dependency extra in `backend/pyproject.toml`.
- Added deterministic offline unit tests with typed fakes covering env handling, request construction, system prompt mapping, usage mapping, invalid response/usage handling, and retry behavior.
- Updated the root `.env` placeholder file to include `ANTHROPIC_API_KEY` alongside the existing OpenAI placeholder.

## Validation Note
- `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m pytest tests/llm/ --cov=llm --cov-report=term-missing` ✅ — 38 passed, `llm` coverage 92%
- `cd /home/rdhagan92/chiliAI/backend && .venv/bin/python -m ruff check llm tests/llm` ✅
- `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pyright llm tests/llm` ✅ — 0 errors, 0 warnings, 0 informations
