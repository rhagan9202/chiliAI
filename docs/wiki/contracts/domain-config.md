# Domain Configuration Contract

**Verified against codebase:** 2026-05-28
**Source:** `backend/config/schema.py`, `backend/config/loader.py`
**Frontend mirror:** `chili_app/src/types/domainConfig.ts`

The `DomainConfig` Pydantic model is the single configuration surface that retargets the platform to a new domain. It is loaded from a YAML/JSON file ("domain pack") resolved with strict precedence: active-pack pointer (`data/config/active_pack.json`, written by admin hot-swaps) > `CHILI_CONFIG_PATH` env var > error. Packs can be hot-swapped at runtime via `POST /config/apply|switch` (see `docs/architecture.md` §9.3).

---

## Top-level: `DomainConfig`

```python
class DomainConfig(BaseModel):
    schema_version: str = "1.0"
    domain: DomainInfo
    entities: list[EntityDefinition]              # from shared/types.py
    relationships: list[RelationshipDefinition]   # from shared/types.py
    capabilities: CapabilitiesConfig
    ingestion: IngestionConfig
    graph: GraphDbConfig | None = None            # defaults to in_memory
    vectorstore: VectorStoreConfig | None = None  # defaults to in_memory, dim=384
    llm: LlmConfig | None = None                  # defaults to local
    embeddings: EmbeddingsConfig | None = None    # defaults to sentence_transformers
    storage: ObjectStoreConfig | None = None      # defaults to local
    events: EventBusConfig | None = None          # defaults to in_memory
    database: DatabaseConfig | None = None        # defaults to in_memory
    monitoring: MonitoringConfig | None = None    # defaults applied
    rag: RagConfig | None = None                  # defaults applied
    auth: AuthConfig | None = None                # disabled by default
    validation: ValidationConfig | None = None    # defaults applied
    records: RecordsConfig | None = None          # empty feeds list
    analytics: AnalyticsConfig | None = None      # defaults applied
    alerts: AlertsConfig                          # required: no default
    ui: UiConfig | None = None
```

**Cross-validation** (enforced by `_validate_cross_references` model_validator):
- `vectorstore.dimensions` must equal `embeddings.dimensions` when both are set.
- No duplicate entity or relationship names.
- Relationship `source`/`target` must reference declared entity names.
- `enum` property types must declare `enum_values`.
- Records feed id/entity/relationship fields cross-referenced against declared schema.

---

## Sub-models

### `DomainInfo`
```python
class DomainInfo(BaseModel):
    name: str
    display_name: str
    description: str
```

### `CapabilitiesConfig`
```python
class CapabilitiesConfig(BaseModel):
    timeseries: bool = False
    gnn: bool = False
    risk_scoring: bool = False
    rag_chat: bool = False
    explainability: bool = False
    structured_ingestion: bool = False
```
Feature gates consumed by frontend via `GET /config/features`.

### `ChunkingConfig`
```python
class ChunkingConfig(BaseModel):
    strategy: Literal["recursive", "fixed_size", "sentence"] = "recursive"
    chunk_size: int = 1000          # > 0
    chunk_overlap: int = 200        # >= 0, must be < chunk_size
    min_chunk_size: int = 50        # > 0, must be <= chunk_size
    record_template: str | None = None
```

### `IngestionConfig`
```python
class IngestionConfig(BaseModel):
    sources: list[IngestionSourceConfig]
    chunking: ChunkingConfig = ChunkingConfig()
```

### `IngestionSourceConfig`
```python
class IngestionSourceConfig(BaseModel):
    type: Literal["file_upload", "api_push"]
    formats: list[str] | None = None
    format: str | None = None
    endpoint: str | None = None
```

### `GraphDbConfig`
```python
class GraphDbConfig(BaseModel):
    backend: Literal["neo4j", "in_memory"] = "in_memory"
    uri: str | None = None
    pool_size: int = 10
    auth_env_var: str | None = None     # name of env var holding Neo4j password
```

### `VectorStoreConfig`
```python
class VectorStoreConfig(BaseModel):
    backend: Literal["qdrant", "in_memory"] = "in_memory"
    uri: str | None = None
    dimensions: int = 384              # > 0, must match EmbeddingsConfig.dimensions
    distance_metric: Literal["cosine", "dot", "euclidean"] = "cosine"
```

### `LlmConfig` (updated 2026-05-22)
```python
class LlmConfig(BaseModel):
    provider: Literal["openai", "anthropic", "local", "ollama"] = "local"
    model: str = "local-default"
    api_key_env_var: str | None = None
    base_url: str | None = None        # used by ollama and any provider needing a custom endpoint
    temperature: float = 0.7           # [0.0, 2.0]
    max_tokens: int = 4096             # > 0
    fallback: "LlmConfig | None" = None  # self-referential; enables fallback chains
```

`"ollama"` provider uses `base_url` (defaults to `http://localhost:11434` in the factory when unset). `fallback` enables ordered fallback chains: `create_llm_client` wraps the primary in `FallbackLlmClient` when `fallback` is set; chains are resolved recursively. See [modules/llm.md](../modules/llm.md) for adapter details.

### `EmbeddingsConfig`
```python
class EmbeddingsConfig(BaseModel):
    provider: Literal["openai", "sentence_transformers", "local"] = "sentence_transformers"
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384              # > 0
    batch_size: int = 32               # > 0
    api_key_env_var: str | None = None
```

### `ObjectStoreConfig`
```python
class ObjectStoreConfig(BaseModel):
    backend: Literal["s3", "minio", "local"] = "local"
    endpoint_url: str | None = None
    bucket: str | None = None
    base_path: str | None = None
    credentials_env_var: str | None = None
```

### `EventBusConfig`
```python
class EventBusConfig(BaseModel):
    backend: Literal["redis", "in_memory"] = "in_memory"
    uri: str | None = None
    stream_prefix: str = "chili"
    consumer_group: str = "chili-workers"
```

### `DatabaseConfig`
```python
class DatabaseConfig(BaseModel):
    backend: Literal["postgres", "in_memory"] = "in_memory"
    dsn_env_var: str = "DATABASE_URL"
    pool_size: int = 10                 # > 0
    pool_max_overflow: int = 5          # >= 0
    statement_timeout_ms: int = 30000   # > 0
```

### `MonitoringConfig`
```python
class MonitoringConfig(BaseModel):
    evaluation_interval_seconds: int = 300    # > 0
    dedup_window_seconds: int = 3600          # > 0
    max_alerts_per_entity: int = 10           # > 0
    max_alerts_per_evaluation: int = 100      # > 0
    grouping_window_seconds: int = 300        # > 0
```

### `AnalyticsConfig`
```python
class AnalyticsConfig(BaseModel):
    metrics_recompute_min_interval_seconds: int = 300   # > 0
```

### `RagConfig`
```python
class RagConfig(BaseModel):
    top_k: int = 5                          # > 0
    expansion_depth: int = 2                # >= 0
    reranking_enabled: bool = False
    system_prompt_template: str | None = None
```

### `AlertsConfig`
```python
class AlertsConfig(BaseModel):
    thresholds: dict[str, dict[str, float]]   # entity_type -> metric_name -> threshold
```

### `AuthConfig`
```python
class AuthConfig(BaseModel):
    enabled: bool = False
    issuer_url: str | None = None
    audience: str | None = None
    jwks_uri: str | None = None
    roles_claim: str = "roles"
    jwks_cache_seconds: int = 3600          # > 0
    client_id: str | None = None
    client_secret_env_var: str | None = None
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    end_session_endpoint: str | None = None
    scopes: list[str] = ["openid", "email", "profile"]
    redirect_uri: str | None = None
    cookie_secure: bool = True
    cookie_domain: str | None = None
    session_ttl_seconds: int = 3600         # > 0
```

### `ValidationConfig`
```python
class ValidationConfig(BaseModel):
    max_file_size_mb: int = 50                    # > 0
    allowed_content_types: list[str] = [          # default list includes PDF, DOCX, XLSX, JSON, CSV, TXT
        "text/plain", "text/csv", "application/json",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]
    max_query_length: int = 10000               # > 0
    max_rag_question_length: int = 5000         # > 0
```

### `RecordsConfig`
```python
class RecordsConfig(BaseModel):
    feeds: list[RecordFeedConfig] = []
```

### `RecordFeedConfig`
```python
class RecordFeedConfig(BaseModel):
    name: str
    record_type: str
    source: Literal["file_upload", "api_push"]
    id_field: str
    record_schema: dict[str, PropertyDefinition] = {}
    entities: list[RecordEntityMapping] = []
    relationships: list[RecordRelationshipMapping] = []
    observations: list[RecordObservationMapping] = []
```

### `UiConfig`
```python
class UiConfig(BaseModel):
    default_entity_type: str | None = None
    navigation: UiNavigationConfig | None = None
    display_fields: dict[str, UiDisplayFieldsConfig] = {}
    roles: dict[str, UiRoleConfig] = {}
```

---

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|---------|
| `CHILI_CONFIG_PATH` | Path to domain YAML/JSON pack when no active-pack pointer exists | Yes, unless a pointer is persisted (no silent default) |
| `CHILI_ACTIVE_PACK_STATE_PATH` | Location of the active-pack pointer state file (default `data/config/active_pack.json`) | No |
| `CHILI_ENV` | Runtime environment: `local`, `dev`, `staging`, `production` | Yes |
| `DATABASE_URL` | Postgres DSN (overridden by `DatabaseConfig.dsn_env_var`) | When `database.backend=postgres` |
| `NEO4J_PASSWORD` | Neo4j auth (env var name set in `GraphDbConfig.auth_env_var`) | When `graph.backend=neo4j` |
| `OPENAI_API_KEY` | OpenAI key (env var name set in `LlmConfig.api_key_env_var`) | When `llm.provider=openai` |
| `ANTHROPIC_API_KEY` | Anthropic key (env var name set in config) | When `llm.provider=anthropic` |
| `JWT_SIGNING_KEY` | JWT signing key for session cookies | When `auth.enabled=true` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | Optional (defaults to localhost:5173) |
| `CHILI_WORKFLOW_RUN_STORE_BACKEND` | `redis` or `in_memory` for workflow run state | Optional |
| `CHILI_KB_REPOSITORY_BACKEND` | `in_memory` or `object_store` for KB/document metadata | Optional |
| `CHILI_EVENT_BUS_BACKEND` | Runtime event bus backend (`in-memory` or `redis`) when config does not explicitly set `events` | Optional |
| `CHILI_EVENT_STREAM_PREFIX` | Redis stream prefix used by event bus runtime settings | Optional |
| `CHILI_EVENT_RECLAIM_MIN_IDLE_MS` | Redis stream pending-message reclaim idle threshold | Optional |
| `CHILI_WORKFLOW_STALE_MAX_AGE_SECONDS` | Enables stale workflow reconciliation when set to a positive integer | Optional |
| `CHILI_WORKFLOW_RECONCILE_INTERVAL_SECONDS` | Worker stale workflow reconciliation interval | Optional |

> **No `CHILI_ALERT_REPOSITORY_BACKEND`.** Alerts read/write directly against
> the durable `alert_history` table (alerts.36) via `AlertFeedStoreProtocol` —
> there is no separate alert projection to select a backend for. Like
> `CaseRepository`, the store picks Postgres automatically when
> `DATABASE_URL`/`database.backend=postgres` resolves a connection provider,
> and falls back to an in-memory adapter otherwise; there is no dedicated env
> var.

---

## Default Config Files

Located in `backend/config/defaults/` (complete, independently loadable packs):
- `medicare_fraud.yaml` — full Medicare fraud detection domain
- `medicare_fraud_cms_desynpuf.yaml` — DE-SynPUF / NPPES exemplar (updated 2026-05-22; see below)
- `food_supply_chain.yaml` — food supply chain domain example
- `department_air_force_housing.yaml` — Department of the Air Force housing oversight

`backend/config/overlays/medicare_fraud_dev.yaml` — dev/test overlay over
`medicare_fraud.yaml`, applied via `CHILI_CONFIG_OVERLAY_PATH` (ADR 0001:
`docs/architecture/decisions/0001-config-overlay-merge-semantics.md`). It is
a partial config (no `entities`/`relationships`/etc.), not a standalone pack.

### `medicare_fraud_cms_desynpuf.yaml` feed inventory (2026-05-22)

The exemplar config now defines 3+ feeds and populates `natural_key` for all four entity types:

| Entity | `natural_key` fields |
|--------|---------------------|
| `provider` | `[npi]` |
| `beneficiary` | `[hic_number]` |
| `claim` | `[claim_id]` |
| `facility` | `[facility_id]` |

Feeds defined in `records.feeds`:

| Feed name | `record_type` | Source |
|-----------|--------------|--------|
| `inpatient_claims` | `inpatient_claim_record` | `file_upload` |
| `outpatient_claims` | `outpatient_claim_record` | `file_upload` |
| `nppes_providers` | (NPPES provider records) | `file_upload` |

The `provider` entity in this config also gains 11 NPPES properties (NPI, provider name fields, taxonomy codes, practice address, etc.) sourced from the NPPES public use file.

The `llm:` section sets OpenAI as the primary provider with an Ollama fallback:
```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  api_key_env_var: OPENAI_API_KEY
  fallback:
    provider: ollama
    model: llama3
    base_url: http://ollama:11434
```

---

## Frontend API

The frontend fetches config at startup:
- `GET /config/domain` → raw `DomainConfig` as JSON dict
- `GET /config/features` → feature flags + page metadata
- `GET /config/domain/schema` → Pydantic JSON schema for the `DomainConfig` model

Frontend TypeScript mirror: `chili_app/src/types/domainConfig.ts`
