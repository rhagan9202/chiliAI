# Story E1-S05: Add vector store configuration section to DomainConfig

## Story
As a platform operator, I want a `VectorStoreConfig` section in the domain configuration, so that the vector store backend, connection, and dimensionality are config-driven.

## Acceptance Criteria
1. `config/schema.py` defines `VectorStoreConfig` with fields: `backend: Literal["qdrant", "pgvector", "in_memory"]`, `uri: str | None`, `dimensions: int = 384`, `distance_metric: Literal["cosine", "dot", "euclidean"] = "cosine"`.
2. `DomainConfig` has `vectorstore: VectorStoreConfig | None = None`.
3. Config loading defaults to `in_memory` when absent.
4. Unit test validates the new section.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/config/schema.py` — add `VectorStoreConfig` model, add `vectorstore` field to `DomainConfig`, update `__all__`
- `backend/config/defaults/medicare_fraud.yaml` — add commented `vectorstore:` section example
- `backend/config/defaults/food_supply_chain.yaml` — add commented `vectorstore:` section example
- `backend/tests/config/test_schema.py` — add tests for `VectorStoreConfig` and round-trip serialization

## Reference Files to Read First
- `backend/config/schema.py` — current `DomainConfig` structure, existing sub-models, model validators, and `__all__` exports
- `backend/config/loader.py` — how config loading works
- `backend/config/defaults/medicare_fraud.yaml` — current YAML fixture structure
- `backend/config/defaults/food_supply_chain.yaml` — second default fixture
- `backend/tests/config/test_schema.py` — existing test patterns for config validation

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase — `VectorStoreConfig` should be a `BaseModel` sub-model
- `dimensions` must match the embedding model output size — add a note/comment that cross-validation with `EmbeddingsConfig.dimensions` will be added in E1-S06
- `uri` should be `str | None = None` (not needed for `in_memory` backend)
- `dimensions` must have `Field(default=384, gt=0)` to enforce positive values
- The `vectorstore` field on `DomainConfig` must be `VectorStoreConfig | None = None` so existing configs still load

## What NOT To Do
- Do NOT implement any vector store adapter or connection logic
- Do NOT add the cross-field validator for `EmbeddingsConfig.dimensions` — that belongs to E1-S06
- Do NOT add other config sections (graph, LLM, etc.) — those are separate stories (E1-S04 handles graph)
- Do NOT break existing config loading
- Do NOT modify any files outside the target files listed above

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=config tests/config/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
