# Story E3-S01: Qdrant Vector Store Adapter

## Story
As a platform operator, I want a Qdrant adapter implementing `VectorStoreProtocol`, so that vector similarity search is backed by a scalable, production-grade engine.

**Status:** Complete on April 20, 2026.

## Acceptance Criteria
1. `vectorstore/adapters/qdrant_adapter.py` implements `VectorStoreProtocol` (upsert_records, search, delete_records).
2. Connection is configured via `VectorStoreConfig` (uri, distance_metric).
3. Collections are created per `knowledge_base_id` with the configured `dimensions` and `distance_metric`.
4. `search` supports metadata filter translation to Qdrant filter syntax.
5. `qdrant-client` is listed as an optional dependency.
6. Integration test (marked `@pytest.mark.integration`) verifies upsert → search round-trip.

## Priority / Size / Dependencies
- **Priority:** P1
- **Size:** M
- **Dependencies:** E1-S05

## Target Files
- `backend/vectorstore/adapters/qdrant_adapter.py` — **create** — Qdrant adapter implementing `VectorStoreProtocol`
- `backend/vectorstore/adapters/__init__.py` — **modify** — re-export `QdrantVectorStore`
- `backend/pyproject.toml` — **modify** — add `qdrant-client[grpc]` as optional dependency under an extras group (e.g., `[qdrant]`)
- `backend/tests/vectorstore/test_qdrant_adapter.py` — **create** — integration test for upsert → search round-trip

## Reference Files to Read First
- `backend/vectorstore/protocols.py` — `VectorStoreProtocol` definition (the contract to implement)
- `backend/vectorstore/models.py` — domain models (`VectorRecord`, etc.)
- `backend/vectorstore/service_models.py` — service request/response models
- `backend/vectorstore/exceptions.py` — module-specific exceptions
- `backend/vectorstore/adapters/in_memory.py` — reference implementation of `VectorStoreProtocol`
- `backend/config/schema.py` — `VectorStoreConfig` (uri, distance_metric, dimensions)
- `backend/shared/types.py` — shared domain types
- `backend/pyproject.toml` — existing dependency structure and optional extras

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase (mirror `InMemoryVectorStore` structure)
- Use `qdrant_client.QdrantClient` with gRPC transport for performance
- Parameterize collection naming as `chili_{knowledge_base_id}` to avoid collisions
- Translate metadata filters to Qdrant `models.Filter` / `models.FieldCondition` syntax
- The adapter must be usable without Qdrant installed (optional import with clear error if missing)

## What NOT To Do
- Do not modify `VectorStoreProtocol` — implement it as-is
- Do not add Qdrant as a hard/required dependency — it must be optional
- Do not embed connection logic in service or API layers — keep it in the adapter
- Do not implement caching or connection pooling beyond what `qdrant_client` provides
- Do not add REST transport — use gRPC only as specified
- Do not create utility modules outside `vectorstore/` for Qdrant-specific helpers

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=vectorstore tests/vectorstore/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
