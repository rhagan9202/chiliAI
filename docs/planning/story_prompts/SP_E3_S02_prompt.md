# Story E3-S02: Sentence-Transformers Embeddings Adapter

**Status:** Complete on April 25, 2026.

## Story
As a platform developer, I want an embeddings adapter using `sentence-transformers`, so that the platform can generate high-quality local embeddings without external API calls.

## Acceptance Criteria
1. `embeddings/adapters/sentence_transformers_adapter.py` implements the embeddings protocol: `embed(EmbeddingRequest) -> EmbeddingResult`.
2. Model is loaded once at construction and reused.
3. Batching respects `EmbeddingsConfig.batch_size` — large requests are split internally.
4. The adapter normalizes output vectors to unit length for cosine similarity.
5. `sentence-transformers` is listed as an optional dependency.
6. Unit test uses a small model (`all-MiniLM-L6-v2`) and verifies output dimensions and non-zero vectors.

> Validation note: Unit tests use a deterministic fake model at the
> sentence-transformers boundary so normal CI does not download model weights.
> The adapter keeps `sentence-transformers` optional and raises a clear install
> error when the extra is missing at runtime.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** M
- **Dependencies:** E1-S06

## Target Files
- `backend/embeddings/adapters/sentence_transformers_adapter.py` — **create** — Sentence-Transformers adapter implementing the embeddings protocol
- `backend/embeddings/adapters/__init__.py` — **modify** — re-export `SentenceTransformersEmbedder`
- `backend/pyproject.toml` — **modify** — add `sentence-transformers` as optional dependency under an extras group (e.g., `[sentence-transformers]`)
- `backend/tests/embeddings/test_sentence_transformers_adapter.py` — **create** — unit test verifying dimensions, non-zero vectors, batching, normalization

## Reference Files to Read First
- `backend/embeddings/protocols.py` — embeddings protocol definition (the contract to implement)
- `backend/embeddings/models.py` — domain models (`EmbeddingRequest`, `EmbeddingResult`, etc.)
- `backend/embeddings/service_models.py` — service request/response models
- `backend/embeddings/exceptions.py` — module-specific exceptions
- `backend/embeddings/adapters/in_memory.py` — reference implementation of the embeddings protocol
- `backend/config/schema.py` — `EmbeddingsConfig` (model_name, batch_size, etc.)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryEmbedder` structure)
- Model must be loaded once at `__init__` and reused across calls — no per-request model loading
- Normalize all output vectors to unit length (L2 norm = 1.0) for cosine similarity compatibility
- Internal batching: split large input lists into chunks of `batch_size` and concatenate results
- The adapter must be usable without `sentence-transformers` installed (optional import with clear error if missing)

## What NOT To Do
- Do not modify the embeddings protocol — implement it as-is
- Do not add `sentence-transformers` as a hard/required dependency — it must be optional
- Do not load the model on each `embed` call — load once at construction
- Do not expose GPU/device configuration in this story (CPU default is fine)
- Do not add caching of embeddings — that is a separate concern
- Do not create utility modules outside `embeddings/` for model management

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=embeddings tests/embeddings/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
