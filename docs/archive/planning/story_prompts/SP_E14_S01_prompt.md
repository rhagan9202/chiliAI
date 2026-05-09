# Story E14-S01: Embedder protocol — model introspection, health check, async variant

## Story
As a platform developer, I want the `EmbedderProtocol` to expose model metadata, a health check, and an async embed variant so production adapters can support health probes and non-blocking pipeline workers.

## Acceptance Criteria
1. `embeddings/adapters/protocols.py` adds to `EmbedderProtocol`:
   - `get_model_info() -> EmbeddingModelInfo` — returns `EmbeddingModelInfo(name, dimensions, max_tokens, provider)` (new Pydantic model in `embeddings/models.py`)
   - `health_check() -> bool` — returns `True` if the adapter can connect to its backing service
2. `InMemoryEmbedder` implements `get_model_info()` returning a hardcoded test `EmbeddingModelInfo` and `health_check()` returning `True`.
3. Unit tests cover: `get_model_info()` returns correct shape, `health_check()` returns bool.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/embeddings/adapters/protocols.py` — add `get_model_info`, `health_check` to protocol
- `backend/embeddings/models.py` — add `EmbeddingModelInfo` Pydantic model
- `backend/embeddings/adapters/in_memory.py` — implement new protocol methods
- `backend/tests/embeddings/test_service.py` — add model info and health check tests

## Reference Files to Read First
- `backend/embeddings/adapters/protocols.py` — current `EmbedderProtocol`
- `backend/embeddings/models.py` — existing embeddings models
- `backend/embeddings/adapters/in_memory.py` — current in-memory embedder
- `backend/tests/embeddings/` — existing embeddings tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `EmbeddingModelInfo` fields: `name: str`, `dimensions: int`, `max_tokens: int`, `provider: str`
- `health_check()` must not raise — return `False` on connection failure
- In-memory adapter dimensions must match those used by `embed()` implementations in tests

## What NOT To Do
- Do not add graph-metric hybrid embedding here — that is E14-S02
- Do not add async embed variant here — scope this story to introspection and health only
- Do not modify SentenceTransformers or OpenAI adapters — those are E3-S02 and E3-S03

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=embeddings tests/embeddings/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
