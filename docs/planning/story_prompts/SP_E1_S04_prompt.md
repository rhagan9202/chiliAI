# Story E1-S04: Add graph database configuration section to DomainConfig

## Story
As a platform operator, I want a `GraphDbConfig` section in the domain configuration, so that the graph adapter backend, connection URI, and pool settings are selected from config instead of hardcoded.

## Acceptance Criteria
1. `config/schema.py` defines `GraphDbConfig` with fields: `backend: Literal["neo4j", "memgraph", "in_memory"]`, `uri: str | None`, `pool_size: int = 10`, `auth_env_var: str | None`.
2. `DomainConfig` has an optional `graph: GraphDbConfig | None = None` field.
3. Config loading defaults to `in_memory` when the section is absent.
4. The default YAML fixture in `config/defaults/` is updated with a commented example.
5. Unit test validates round-trip serialize/deserialize of the new section.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/config/schema.py` — add `GraphDbConfig` model, add `graph` field to `DomainConfig`, update `__all__`
- `backend/config/defaults/medicare_fraud.yaml` — add commented `graph:` section example
- `backend/config/defaults/food_supply_chain.yaml` — add commented `graph:` section example
- `backend/tests/config/test_schema.py` — add tests for `GraphDbConfig` and round-trip serialization

## Reference Files to Read First
- `backend/config/schema.py` — current `DomainConfig` structure, existing sub-models (e.g., `CapabilitiesConfig`, `IngestionConfig`), model validators, and `__all__` exports
- `backend/config/loader.py` — how config loading works, to understand default behavior when section is absent
- `backend/config/defaults/medicare_fraud.yaml` — current YAML fixture structure and commenting style
- `backend/config/defaults/food_supply_chain.yaml` — second default fixture
- `backend/tests/config/test_schema.py` — existing test patterns for config validation

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase — `GraphDbConfig` should be a `BaseModel` sub-model like `CapabilitiesConfig`, `IngestionConfig`, etc.
- The `graph` field on `DomainConfig` must be `GraphDbConfig | None = None` so existing configs without the section still load
- `uri` should be `str | None = None` (no connection needed for `in_memory` backend)
- `auth_env_var` stores the name of an environment variable containing credentials — do NOT store actual credentials in config
- YAML comments should follow the existing style in the default fixtures

## What NOT To Do
- Do NOT implement any graph adapter or connection logic — that belongs to the graph module
- Do NOT modify `config/loader.py` unless strictly necessary for default behavior
- Do NOT store actual credentials or secrets in config schema defaults
- Do NOT add other config sections (vectorstore, LLM, etc.) — those are separate stories
- Do NOT break existing config loading — the `graph` field must be optional with `None` default
- Do NOT modify any files outside the target files listed above

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=config tests/config/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
