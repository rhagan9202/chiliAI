# Story E3-S03: OpenAI Embeddings Adapter

## Story
As a platform developer, I want an embeddings adapter calling the OpenAI Embeddings API, so that operators can use cloud-hosted embedding models when local GPU is unavailable.

## Acceptance Criteria
1. `embeddings/adapters/openai_adapter.py` implements the embeddings protocol.
2. API key is read from the environment variable specified in `EmbeddingsConfig.api_key_env_var`.
3. Batching respects the OpenAI per-request token limit (8191 tokens for `text-embedding-3-small`).
4. Rate-limit errors (HTTP 429) trigger exponential backoff retry (max 3 attempts).
5. `openai` is listed as an optional dependency.
6. Unit test mocks the OpenAI client and verifies correct request construction and response parsing.

## Priority / Size / Dependencies
- **Priority:** P2
- **Size:** M
- **Dependencies:** E1-S06

## Target Files
- `backend/embeddings/adapters/openai_adapter.py` — **create** — OpenAI embeddings adapter implementing the embeddings protocol
- `backend/embeddings/adapters/__init__.py` — **modify** — re-export `OpenAIEmbedder`
- `backend/pyproject.toml` — **modify** — add `openai` as optional dependency under an extras group (e.g., `[openai]`) if not already present
- `backend/tests/embeddings/test_openai_adapter.py` — **create** — unit test with mocked OpenAI client

## Reference Files to Read First
- `backend/embeddings/protocols.py` — embeddings protocol definition (the contract to implement)
- `backend/embeddings/models.py` — domain models (`EmbeddingRequest`, `EmbeddingResult`, etc.)
- `backend/embeddings/service_models.py` — service request/response models
- `backend/embeddings/exceptions.py` — module-specific exceptions
- `backend/embeddings/adapters/in_memory.py` — reference implementation of the embeddings protocol
- `backend/config/schema.py` — `EmbeddingsConfig` (api_key_env_var, model_name, batch_size, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryEmbedder` structure)
- Read the API key from `os.environ` using the env var name from `EmbeddingsConfig.api_key_env_var` — never hardcode keys
- Implement exponential backoff retry for HTTP 429 responses (max 3 attempts, e.g., 1s, 2s, 4s)
- Batch inputs to respect the 8191 token-per-request limit for `text-embedding-3-small`
- The adapter must be usable without `openai` installed (optional import with clear error if missing)
- The `openai` optional dependency is shared with E3-S04 (LLM adapter) — coordinate the extras group

## What NOT To Do
- Do not modify the embeddings protocol — implement it as-is
- Do not add `openai` as a hard/required dependency — it must be optional
- Do not hardcode API keys or model names — read from config/environment
- Do not implement token counting precisely — use a conservative character-based estimate or `tiktoken` if already available
- Do not implement streaming — this is an embeddings endpoint, not chat
- Do not add custom HTTP client logic — use the official `openai` Python SDK
- Do not retry on non-rate-limit errors (e.g., 400, 401) — only retry 429

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=embeddings tests/embeddings/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
