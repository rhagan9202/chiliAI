# Story E1-S06: Add LLM, embeddings, storage, events, monitoring, and RAG configuration sections to DomainConfig

## Story
As a platform operator, I want configuration sections for LLM, embeddings, object storage, events, monitoring, and RAG, so that every external subsystem is configurable from a single YAML surface.

## Acceptance Criteria
1. `config/schema.py` defines: `LlmConfig`, `EmbeddingsConfig`, `ObjectStoreConfig`, `EventBusConfig`, `MonitoringConfig`, `RagConfig` with the fields described below.
2. Each section is an optional field on `DomainConfig` that defaults to a sensible in-memory/local value.
3. `schema_version: str = "1.0"` is added to `DomainConfig` for future migration support.
4. Cross-field validator ensures `EmbeddingsConfig.dimensions == VectorStoreConfig.dimensions` when both are present.
5. All existing config tests pass unchanged.

### Config Model Field Specifications

**LlmConfig:**
- `provider: Literal["openai", "anthropic", "local"]`
- `model: str`
- `api_key_env_var: str | None = None`
- `temperature: float = Field(default=0.7, ge=0.0, le=2.0)`
- `max_tokens: int = Field(default=4096, gt=0)`

**EmbeddingsConfig:**
- `provider: Literal["openai", "sentence_transformers", "local"]`
- `model: str = "all-MiniLM-L6-v2"`
- `dimensions: int = Field(default=384, gt=0)`
- `batch_size: int = Field(default=32, gt=0)`
- `api_key_env_var: str | None = None`

**ObjectStoreConfig:**
- `backend: Literal["s3", "gcs", "minio", "local"]`
- `bucket: str | None = None`
- `base_path: str | None = None`
- `credentials_env_var: str | None = None`

**EventBusConfig:**
- `backend: Literal["redis", "in_memory"]`
- `uri: str | None = None`
- `stream_prefix: str = "chili"`
- `consumer_group: str = "chili-workers"`

**MonitoringConfig:**
- `evaluation_interval_seconds: int = Field(default=300, gt=0)`
- `dedup_window_seconds: int = Field(default=3600, gt=0)`
- `max_alerts_per_entity: int = Field(default=10, gt=0)`

**RagConfig:**
- `top_k: int = Field(default=5, gt=0)`
- `expansion_depth: int = Field(default=2, ge=0)`
- `reranking_enabled: bool = False`
- `system_prompt_template: str | None = None`

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E1-S04, E1-S05 |

## Target Files
- `backend/config/schema.py` — add 6 new config sub-models, add fields to `DomainConfig`, add cross-field validator, add `schema_version`, update `__all__`
- `backend/config/defaults/medicare_fraud.yaml` — add commented sections for all new config areas
- `backend/config/defaults/food_supply_chain.yaml` — add commented sections for all new config areas
- `backend/tests/config/test_schema.py` — add tests for each new config model, cross-field validation, schema_version

## Reference Files to Read First
- `backend/config/schema.py` — current `DomainConfig` and all existing sub-models including `GraphDbConfig` and `VectorStoreConfig` (from E1-S04, E1-S05)
- `backend/config/loader.py` — how config loading works
- `backend/config/defaults/medicare_fraud.yaml` — current YAML fixture
- `backend/config/defaults/food_supply_chain.yaml` — second fixture
- `backend/events/runtime.py` — current `EventBusSettings` model to align `EventBusConfig` fields
- `backend/tests/config/test_schema.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase — each config model is a `BaseModel` sub-model
- All `*_env_var` fields store environment variable **names**, not actual secrets
- The cross-field validator for `EmbeddingsConfig.dimensions == VectorStoreConfig.dimensions` must only trigger when **both** sections are present and non-None
- Each new `DomainConfig` field must be `Optional` with `None` default to maintain backward compatibility
- `schema_version` should have a default so existing configs without it still load
- Use `from __future__ import annotations` (already present)

## What NOT To Do
- Do NOT implement any adapter or connection logic for these subsystems
- Do NOT modify `events/runtime.py` or remove `EventBusSettings` — the two may coexist until a migration story
- Do NOT store actual credentials or secrets in config defaults
- Do NOT break existing config loading or existing tests
- Do NOT add config sections beyond the 6 specified
- Do NOT modify `config/loader.py` unless strictly necessary for defaults
- Do NOT modify any files outside the target files listed above

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=config tests/config/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)
