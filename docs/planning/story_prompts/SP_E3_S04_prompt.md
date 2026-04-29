# Story E3-S04: OpenAI LLM Adapter

## Story
As a platform developer, I want an LLM adapter calling the OpenAI Chat Completions API, so that the RAG chat and analytics explainability modules can generate natural-language outputs.

## Acceptance Criteria
1. `llm/adapters/openai_adapter.py` implements the LLM protocol: `generate(GenerationRequest) -> GenerationResult`.
2. API key is read from the environment variable specified in `LlmConfig.api_key_env_var`.
3. Token usage (prompt_tokens, completion_tokens) is captured in `CompletionMetadata`.
4. Rate-limit errors trigger exponential backoff retry (max 3 attempts).
5. `openai` is listed as an optional dependency (shared with E3-S03).
6. Unit test mocks the OpenAI client and verifies request/response mapping.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** M
- **Dependencies:** E1-S06

## Target Files
- `backend/llm/adapters/openai_adapter.py` — **create** — OpenAI LLM adapter implementing the LLM protocol
- `backend/llm/adapters/__init__.py` — **modify** — re-export `OpenAILlmClient`
- `backend/pyproject.toml` — **modify** — add `openai` as optional dependency if not already present (shared extras group with E3-S03)
- `backend/tests/llm/test_openai_adapter.py` — **create** — unit test with mocked OpenAI client

## Reference Files to Read First
- `backend/llm/protocols.py` — LLM protocol definition (the contract to implement)
- `backend/llm/models.py` — domain models (`GenerationRequest`, `GenerationResult`, `CompletionMetadata`, etc.)
- `backend/llm/service_models.py` — service request/response models
- `backend/llm/exceptions.py` — module-specific exceptions
- `backend/llm/adapters/in_memory.py` — reference implementation of the LLM protocol
- `backend/config/schema.py` — `LlmConfig` (`api_key_env_var`, `model`, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryLlmClient` structure)
- Read the API key from `os.environ` using the env var name from `LlmConfig.api_key_env_var` — never hardcode keys
- Implement exponential backoff retry for HTTP 429 responses (max 3 attempts)
- Map OpenAI `usage.prompt_tokens` and `usage.completion_tokens` to `CompletionMetadata`
- Support `gpt-4o` and `gpt-4o-mini` via config — do not hardcode model names
- The adapter must be usable without `openai` installed (optional import with clear error if missing)
- The `openai` optional dependency is shared with E3-S03 (embeddings adapter)

## What NOT To Do
- Do not modify the LLM protocol — implement it as-is
- Do not add `openai` as a hard/required dependency — it must be optional
- Do not hardcode API keys or model names — read from config/environment
- Do not implement streaming in this story — non-streaming only
- Do not implement function calling or tool use — plain chat completions only
- Do not add custom HTTP client logic — use the official `openai` Python SDK
- Do not retry on non-rate-limit errors (e.g., 400, 401) — only retry 429

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=llm tests/llm/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
