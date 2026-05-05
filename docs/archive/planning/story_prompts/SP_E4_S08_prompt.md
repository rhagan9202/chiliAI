# Story E4-S08: Config-driven adapter wiring in the worker coordinator

## Story
As a platform developer, I want `build_worker_dependencies()` to select adapters from `DomainConfig` instead of hardcoding in-memory implementations.

## Acceptance Criteria
1. `build_worker_dependencies()` reads `DomainConfig` subsystem sections and selects matching adapters for object store, graph repository, embeddings, vector store, and LLM.
2. Falls back to in-memory adapters when config sections are absent (preserving current test behavior).
3. Adapter construction failures raise clear `ConfigurationError` exceptions with the subsystem name and backend value.
4. Unit test verifies that removing a config section falls back to in-memory.

## Priority / Size / Dependencies
| Field        | Value       |
|--------------|-------------|
| Priority     | P1          |
| Size         | M           |
| Dependencies | E1-S07      |

## Target Files
- `backend/agent/coordinator.py` — refactor `build_worker_dependencies()` to read `DomainConfig` and select adapters
- `backend/agent/exceptions.py` — add `ConfigurationError` if not already present
- `backend/api/dependencies.py` — align shared DI factory patterns if needed
- `backend/tests/agent/test_coordinator.py` — tests for config-driven wiring and in-memory fallback

## Reference Files to Read First
- `backend/agent/coordinator.py` — current `build_worker_dependencies()` implementation
- `backend/config/schema.py` — `DomainConfig` structure and subsystem sections
- `backend/config/loader.py` — config loading utilities
- `backend/agent/exceptions.py` — existing exception types
- `backend/api/dependencies.py` — existing DI factory patterns for adapter selection
- `backend/storage/adapters/` — available object store adapters
- `backend/graph/adapters/` — available graph adapters
- `backend/embeddings/adapters/` — available embeddings adapters
- `backend/vectorstore/adapters/` — available vector store adapters (if present)
- `backend/llm/adapters/` — available LLM adapters
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- The coordinator is allowed to import adapter constructors since it is the composition root for the worker
- Adapter selection should use a registry or match pattern based on config backend strings (e.g., `"neo4j"`, `"in_memory"`, `"redis"`)
- Fallback to in-memory must be silent and automatic when config sections are absent — no warnings or errors
- `ConfigurationError` must include the subsystem name and the backend value that failed, for clear operator diagnostics
- Follow the same DI patterns established in `api/dependencies.py` where applicable

## What NOT To Do
- Do not remove or break in-memory adapter defaults — they must remain the fallback for testing
- Do not hardcode adapter class references in a long if/elif chain; prefer a registry or mapping pattern
- Do not import adapter implementations at module top level if they have heavy dependencies; use lazy imports
- Do not modify `DomainConfig` schema — consume it as-is
- Do not add new config fields — work with existing subsystem sections
- Do not catch and ignore `ConfigurationError` — let it propagate to fail fast on misconfiguration

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `agent/coordinator.py` now drives adapter
selection from `DomainConfig` via per-subsystem registries
(`_OBJECT_STORE_REGISTRY`, `_GRAPH_REGISTRY`, `_VECTOR_STORE_REGISTRY`,
`_EMBEDDING_REGISTRY`, `_LLM_REGISTRY`). `build_object_store`,
`build_graph_repository`, `build_vector_store`, `build_embedder`, and
`build_llm_client` look up the configured backend, fall back silently to
in-memory when the section equals its post-validator default, and otherwise
delegate to a lazy-import factory. Optional adapter modules
(`Neo4jGraphRepository`, `QdrantVectorStore`, `OpenAIEmbedder`,
`SentenceTransformersEmbedder`, `OpenAILlmClient`, `AnthropicLlmClient`,
`S3ObjectStore`, `LocalFsObjectStore`) are imported lazily and any
`ImportError`, `ValueError`, or domain-specific configuration exception is
re-raised as `agent.exceptions.ConfigurationError(subsystem=..., backend=...,
message=...)`. `build_worker_dependencies()` now returns a
`WorkerDependencies` dataclass that adds `vector_store` and `llm_client`
alongside the existing pipeline subsystems.

## Validation Note
From `backend/`: `pytest tests/agent tests/events tests/api --cov=agent
--cov=events --cov=api --cov-report=term-missing` passed with 91 tests; agent
coverage 87%, events 96%, api 96%. `ruff check agent events api tests/agent
tests/events tests/api` passed. `pyright agent events api tests/agent
tests/events tests/api` reported 0 errors.
