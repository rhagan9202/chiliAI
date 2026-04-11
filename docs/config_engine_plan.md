# Plan: Domain Configuration System

## TL;DR
Implement the full domain configuration system (architecture §9) consisting of four deliverables: (1) the `shared/` module with generic platform types, config-definition types, protocols, and utilities — with **zero hardcoded domain-specific types**; (2) the `config/` module with Pydantic schema, YAML/JSON loader, and validation; (3) example domain configs (`medicare_fraud.yaml`, `food_supply_chain.yaml`); and (4) a proper `api/routers/config.py` endpoint wired into the app factory. All domain entity types (provider, claim, beneficiary, etc.) exist only in the config YAML and flow through the system as generic `Entity` instances whose `type` field and `properties` dict are validated against config at system boundaries.

---

## Phase 1: `shared/` Module — Domain Types, Protocols, Utilities

**Goal**: Create the leaf-dependency contracts library that every other module imports.

### Step 1: Create `backend/shared/__init__.py`
- Re-export key symbols from `types`, `protocols`, `utils` for convenient imports.

### Step 2: Create `backend/shared/types.py` — Platform and config-definition types
Pydantic `BaseModel` classes. **NO hardcoded domain-specific types** (no Claim, Provider, Beneficiary classes). All domain entities are represented at runtime by the generic `Entity` type — its `type` field matches a config-defined `EntityDefinition.name`, and its `properties` dict holds values whose keys match the config-defined property names.

**Config definition types** (describe the schema, loaded from YAML):
- `PropertyType` — Enum: `string`, `integer`, `decimal`, `date`, `list`, `boolean`, `enum`, `nested`
- `PropertyDefinition` — `type: PropertyType`, `display: str`, optional `enum_values: list[str]`
- `EntityDefinition` — `name: str`, `display_label: str`, `icon: str`, `properties: dict[str, PropertyDefinition]`
- `RelationshipDefinition` — `name: str`, `display_label: str`, `source: str`, `target: str`

**Generic runtime types** (domain-agnostic containers):
- `Entity` — `id: str`, `type: str`, `properties: dict[str, Any]`, `metadata: dict[str, Any]` — `entity.type` matches an `EntityDefinition.name` from the active config
- `Relationship` — `id: str`, `type: str`, `source_id: str`, `target_id: str`, `properties: dict[str, Any]` — `relationship.type` matches a `RelationshipDefinition.name`

**Platform types** (domain-agnostic, part of chiliAI itself — not tied to any specific domain):
- `Alert` — `id: str`, `entity_type: str`, `entity_id: str`, `severity: str`, `title: str`, `reasoning: str`, `evidence_pack_id: str | None`, `created_at: datetime`, `acknowledged: bool`
- `EvidencePack` — `id: str`, `alert_id: str`, `reasoning: str`, `subgraph_nodes: list[str]`, `subgraph_edges: list[str]`, `confidence: float`, `scores: dict[str, float]`
- `KnowledgeBase` — `id: str`, `name: str`, `description: str`, `entity_count: int`, `relationship_count: int`, `document_count: int`, `status: str`, `created_at: datetime`

**Runtime validation helper**:
- `validate_entity(entity: Entity, config: DomainConfig) -> list[str]` — Validates that an Entity's `type` exists in config and its properties match the expected schema. Returns list of validation errors (empty = valid). Used at system boundaries (ingestion, API input) — not on every internal pass.

### Step 3: Create `backend/shared/protocols.py` — Cross-cutting protocols
- `Configurable` — Protocol: `configure(config: DomainConfig) -> None` (consumed by modules at init)
- Other protocols will be added as modules are built (EventBus, ObjectStore, etc.)

### Step 4: Create `backend/shared/utils.py` — Small utilities
- `generate_id() -> str` — UUID4-based ID generator
- `normalize_text(text: str) -> str` — Lowercase, strip, collapse whitespace

### Step 5: Create `backend/tests/shared/test_types.py`
- Validate construction of all domain types
- Validate enum values for `PropertyType`
- Validate `EntityDefinition` / `RelationshipDefinition` serialization round-trip
- ≥ 85% coverage for shared package

---

## Phase 2: `config/` Module — Schema, Loader, Validation

**Goal**: Parse and validate YAML/JSON domain configuration into typed Pydantic models.

### Step 6: Create `backend/config/__init__.py`
- Re-export `DomainConfig`, `load_config`.

### Step 7: Create `backend/config/schema.py` — Pydantic config models
All Pydantic `BaseModel` classes:

- `DomainInfo` — `name: str`, `display_name: str`, `description: str`
- `CapabilitiesConfig` — `timeseries: bool`, `gnn: bool`, `risk_scoring: bool`, `rag_chat: bool`, `explainability: bool`
- `IngestionSourceConfig` — `type: Literal["file_upload", "api_push"]`, `formats: list[str] | None`, `format: str | None`, `endpoint: str | None`
- `IngestionConfig` — `sources: list[IngestionSourceConfig]`
- `EntityThreshold` — dynamic: `risk_score: float | None`, `anomaly_sigma: float | None`, `amount_percentile: float | None`
- `AlertsConfig` — `thresholds: dict[str, dict[str, float]]`
- `DomainConfig` — top-level: `domain: DomainInfo`, `entities: list[EntityDefinition]`, `relationships: list[RelationshipDefinition]`, `capabilities: CapabilitiesConfig`, `ingestion: IngestionConfig`, `alerts: AlertsConfig`

Validation (Pydantic `model_validator`):
- All relationship `source`/`target` values must reference a declared entity name
- No duplicate entity names
- No duplicate relationship names
- Property `enum_values` required when type is `enum`

### Step 8: Create `backend/config/loader.py` — Config loading
- `load_config(path: str | Path | None = None) -> DomainConfig`
  - Reads `CHILI_CONFIG_PATH` env var if path not provided
  - Supports `.yaml`/`.yml` and `.json` file extensions
  - Parses file content, validates via `DomainConfig` Pydantic model
  - Raises `ConfigLoadError` (custom exception) on file-not-found, parse error, or validation failure
- `ConfigLoadError` — Custom exception with clear error messages

### Step 9: Create `backend/config/defaults/medicare_fraud.yaml`
- Full YAML matching architecture §9.1 exactly (entities: provider, beneficiary, claim, facility; relationships: submitted_by, billed_for, performed_at, referred_by; all capabilities enabled; ingestion sources; alert thresholds)

### Step 10: Create `backend/config/defaults/food_supply_chain.yaml`
- Alternative domain example per architecture §9.3 (entities: supplier, shipment, inspection, facility; relationships: shipped_by, inspected_at, supplied_by; capabilities subset)

### Step 11: Create `backend/tests/config/test_schema.py`
- Valid config round-trip (load YAML → DomainConfig → dict → back)
- Relationship source/target validation (reject invalid references)
- Duplicate entity name rejection
- Duplicate relationship name rejection
- Missing required fields
- Each property type enum value

### Step 12: Create `backend/tests/config/test_loader.py`
- Load from file path (using medicare_fraud.yaml default)
- Load from env var
- JSON file loading
- File not found → ConfigLoadError
- Invalid YAML → ConfigLoadError
- Schema validation failure → ConfigLoadError
- ≥ 85% coverage for config package

---

## Phase 3: API Router — Serve Config to Frontend

**Goal**: Replace the inline stub with a proper `/config/domain` endpoint backed by the real config loader.

### Step 13: Create `backend/api/routers/__init__.py`

### Step 14: Create `backend/api/routers/config.py`
- `router = APIRouter(prefix="/config", tags=["configuration"])`
- `GET /config/domain` → loads `DomainConfig`, returns as JSON (Pydantic model serialization)
- Uses FastAPI dependency injection: `config_dep` that calls `load_config()` once and caches (lifespan or `lru_cache`)

### Step 15: Create `backend/api/dependencies.py`
- `get_domain_config() -> DomainConfig` — Singleton-cached config loader. Reads config once at startup, returns cached instance on subsequent calls.

### Step 16: Update `backend/api/app.py`
- Remove the inline `/config/domain` stub
- Import and include `config_router`
- Wire `get_domain_config` as a lifespan or startup dependency

### Step 17: Create `backend/tests/api/test_config_router.py`
- `GET /config/domain` returns 200 with valid DomainConfig JSON
- Response contains expected entity names, relationship names, capabilities
- Uses HTTPX TestClient + FastAPI test overrides

---

## Phase 4: Dependency & Documentation Updates

### Step 18: Update `backend/pyproject.toml`
- Add `pyyaml>=6.0` to dependencies

### Step 19: Add pytest configuration to `backend/pyproject.toml`
```
[tool.pytest.ini_options]
testpaths = ["tests"]
```

### Step 20: Update `backend/README.md`
- Update "Current State" to reflect the new shared/ and config/ modules
- Document configuration: how to set CHILI_CONFIG_PATH, available defaults

### Step 21: Update `docker-compose.dev.yaml` and `docker-compose.yaml`
- Mount `backend/config/defaults/medicare_fraud.yaml` to `/config/medicare_fraud.yaml` inside api and worker containers (or update CHILI_CONFIG_PATH to point to the correct path within the container)

*Step 18 parallel with Steps 13-17. Steps 19-21 depend on tests passing.*

---

## Relevant Files

### New files
| File | Purpose |
|------|---------|
| `backend/shared/__init__.py` | Module init, re-exports |
| `backend/shared/types.py` | Generic platform types (Entity, Relationship, Alert, etc.) + config definition types (EntityDefinition, PropertyDefinition, etc.) — NO domain-specific types |
| `backend/shared/protocols.py` | Configurable protocol and future cross-cutting protocols |
| `backend/shared/utils.py` | generate_id(), normalize_text() |
| `backend/config/__init__.py` | Module init, re-exports |
| `backend/config/schema.py` | DomainConfig Pydantic model + validation |
| `backend/config/loader.py` | load_config() + ConfigLoadError |
| `backend/config/defaults/medicare_fraud.yaml` | Full working example matching §9.1 |
| `backend/config/defaults/food_supply_chain.yaml` | Alternative domain example |
| `backend/api/routers/__init__.py` | Routers package init |
| `backend/api/routers/config.py` | GET /config/domain endpoint |
| `backend/api/dependencies.py` | DI wiring: get_domain_config() |
| `backend/tests/__init__.py` | Tests package |
| `backend/tests/shared/__init__.py` | Tests sub-package |
| `backend/tests/shared/test_types.py` | Domain type tests |
| `backend/tests/config/__init__.py` | Tests sub-package |
| `backend/tests/config/test_schema.py` | Config validation tests |
| `backend/tests/config/test_loader.py` | Config loading tests |
| `backend/tests/api/__init__.py` | Tests sub-package |
| `backend/tests/api/test_config_router.py` | API endpoint tests |

### Modified files
| File | Change |
|------|--------|
| `backend/pyproject.toml` | Add `pyyaml>=6.0`, pytest config |
| `backend/api/app.py` | Remove inline stub, include config router |
| `backend/README.md` | Update current state, document config |
| `docker-compose.dev.yaml` | Mount config file or fix path |
| `docker-compose.yaml` | Mount config file or fix path |

---

## Verification

1. **Unit tests pass**: `cd backend && pytest tests/ --cov -v` — all green, ≥85% coverage for `shared/` and `config/`
2. **Load default config**: `python -c "from config.loader import load_config; c = load_config('config/defaults/medicare_fraud.yaml'); print(c.domain.display_name)"` → "Medicare Fraud Detection"
3. **API endpoint**: Start the dev server, `curl http://localhost:8000/config/domain` → full JSON config with entities, relationships, capabilities
4. **Validation**: Invalid YAML (e.g., relationship referencing non-existent entity) → clear `ConfigLoadError`
5. **Docker**: `make dev` → API container starts with config loaded; `curl localhost:8000/config/domain` returns full config
6. **Type checking**: `pyright --strict` passes on all new files (or code is structured to satisfy strict mode)

---

## Decisions
- **Richer property types** — Support boolean, enum, nested in addition to string/integer/decimal/date/list (user confirmed)
- **Zero hardcoded domain-specific types** — No `Claim`, `Provider`, `Beneficiary` classes. All domain entities use the generic `Entity(type, properties)` container validated against config at system boundaries. This is a deliberate deviation from architecture §5's `shared/types.py` listing, which named these types — we implement the spirit (config-driven reconfigurability) over the letter (user confirmed)
- **PyYAML pinned explicitly** in pyproject.toml (user confirmed)
- **Full shared/ module** created — types.py, protocols.py, utils.py per architecture §5 (user confirmed)
- **Proper config router** — api/routers/config.py replacing inline stub (user confirmed)
- **Config depends only on shared/** — follows module dependency rules from architecture §5.2
- **Pydantic model_validator** for cross-field validation (relationship source/target references, uniqueness)
- **Config cached as singleton** — loaded once at startup, shared via DI
- **`ConfigLoadError`** custom exception wraps file/parse/validation errors
- **Tests in backend/tests/** following pytest conventions with ≥85% coverage target

## Further Considerations
1. **Config hot-reload**: Currently config is loaded once at startup. A future enhancement could watch the file and reload on change (SIGHUP or file watcher). Excluded from this plan — restart is the mechanism.
