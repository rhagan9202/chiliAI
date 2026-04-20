# Story E1-S07: Config-driven adapter selection in the DI layer

## Story
As a platform developer, I want `api/dependencies.py` to select adapter implementations based on `DomainConfig` subsystem sections, so that switching from in-memory to production adapters requires only a config change.

## Acceptance Criteria
1. For each subsystem (graph, vectorstore, embeddings, llm, storage, events, monitoring), `api/dependencies.py` contains a factory function that reads the corresponding `DomainConfig` section and returns the appropriate adapter instance.
2. When a config section is absent (`None`), the factory defaults to the in-memory/local adapter.
3. When a config section specifies a backend that has no registered adapter, the factory raises `ConfigurationError` with a clear message listing available backends.
4. Existing DI functions (`get_domain_config`, `get_object_store`, `get_event_bus`, etc.) continue to work unchanged for callers.
5. All existing API tests pass without modification.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E1-S06       |

## Target Files
- `backend/api/dependencies.py` — refactor existing factories and add new factory functions for graph, vectorstore, embeddings, llm, monitoring adapters; all driven by `DomainConfig` sections
- `backend/shared/exceptions.py` — add `ConfigurationError` if not already present (or add to existing exception location)
- `backend/tests/api/test_dependencies.py` — add tests for config-driven adapter selection, default fallback, and `ConfigurationError` cases

## Reference Files to Read First
- `backend/api/dependencies.py` — current DI wiring, existing factory functions, import patterns
- `backend/config/schema.py` — `DomainConfig` with all config sections from E1-S04, E1-S05, E1-S06
- `backend/config/loader.py` — how config loading and `get_domain_config()` work
- `backend/storage/adapters/in_memory.py` — existing in-memory adapter pattern
- `backend/storage/protocols.py` — existing protocol pattern for adapters
- `backend/events/runtime.py` — current `create_event_bus()` factory to understand existing pattern
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/graph/protocols.py` — `GraphRepository` protocol (or equivalent)
- `backend/vectorstore/protocols.py` — vector store protocol
- `backend/embeddings/protocols.py` — embeddings protocol
- `backend/llm/protocols.py` — LLM protocol
- `backend/monitoring/protocols.py` — monitoring protocol
- `backend/tests/api/` — existing API test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase — factory functions with `@lru_cache(maxsize=1)` for singletons
- Each factory must return the **protocol type** (not the concrete adapter type) for loose coupling
- Factory functions must be deterministic: same config → same adapter type
- `ConfigurationError` should be a clear, descriptive exception — not a generic `ValueError`
- Do NOT instantiate production adapters (neo4j, qdrant, etc.) if they don't exist yet — the factory should raise `ConfigurationError` for unimplemented backends, or import them conditionally
- Maintain backward compatibility with existing callers of `get_event_bus()`, `get_object_store()`, etc.

## What NOT To Do
- Do NOT implement actual production adapters (Neo4j, Qdrant, pgvector, etc.) — only wire up the selection logic
- Do NOT modify `config/schema.py` or `config/loader.py`
- Do NOT modify adapter implementations — only the DI wiring
- Do NOT break existing API routes or their tests
- Do NOT add route handlers or new API endpoints
- Do NOT remove the existing `get_event_bus_settings()` or `load_event_bus_settings()` integration — those may still be needed until EventBusConfig migration is complete
- Do NOT modify any files outside the target files listed above

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
