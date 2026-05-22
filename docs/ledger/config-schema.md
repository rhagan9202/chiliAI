# Config Schema Snapshot

**Generated:** 2026-05-22 (merge commit `acae4ac`)
**Source:** `backend/config/schema.py`, `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`

---

## `DomainConfig` Top-Level Fields

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `schema_version` | `str` | no | `"1.0"` | |
| `domain` | `DomainInfo` | yes | — | `name`, `display_name`, `description` |
| `entities` | `list[EntityDefinition]` | yes | — | At least one required |
| `relationships` | `list[RelationshipDefinition]` | yes | — | |
| `capabilities` | `CapabilitiesConfig` | yes | — | Feature flags |
| `ingestion` | `IngestionConfig` | yes | — | Sources + chunking |
| `graph` | `GraphDbConfig \| None` | no | `GraphDbConfig()` | Defaults to in-memory |
| `vectorstore` | `VectorStoreConfig \| None` | no | `VectorStoreConfig()` | Defaults to in-memory |
| `llm` | `LlmConfig \| None` | no | `LlmConfig()` | Defaults to `"local"` provider |
| `embeddings` | `EmbeddingsConfig \| None` | no | `EmbeddingsConfig()` | |
| `storage` | `ObjectStoreConfig \| None` | no | `ObjectStoreConfig()` | |
| `events` | `EventBusConfig \| None` | no | `EventBusConfig()` | |
| `database` | `DatabaseConfig \| None` | no | `DatabaseConfig()` | |
| `monitoring` | `MonitoringConfig \| None` | no | `MonitoringConfig()` | |
| `rag` | `RagConfig \| None` | no | `RagConfig()` | |
| `auth` | `AuthConfig \| None` | no | `AuthConfig()` | |
| `validation` | `ValidationConfig \| None` | no | `ValidationConfig()` | |
| `records` | `RecordsConfig \| None` | no | `RecordsConfig()` | |
| `analytics` | `AnalyticsConfig \| None` | no | `AnalyticsConfig()` | |
| `alerts` | `AlertsConfig` | yes | — | Thresholds dict |
| `ui` | `UiConfig \| None` | no | None | Navigation, display_fields, roles |
| `default_reference_kb_id` | `str \| None` | no | None | Auto-attached "policy graph" KB; enables dual-graph reads when set |

### Key sub-models

**`LlmConfig`** (updated 2026-05-22):
- `provider: Literal["openai", "anthropic", "local", "ollama"]`
- `model: str`
- `api_key_env_var: str | None`
- `base_url: str | None` — used by Ollama and any provider needing a custom endpoint
- `temperature: float` (0.0–2.0)
- `max_tokens: int`
- `fallback: LlmConfig | None` — recursive fallback chain; `llm/factory.py` wraps into `FallbackLlmClient`

**`EntityDefinition`** (updated 2026-05-22):
- `name: str`
- `display_label: str`
- `icon: str`
- `natural_key: list[str]` — property names whose combined value uniquely identifies an entity instance; used by `LlmDocumentExtractor` for intra-chunk deduplication
- `properties: dict[str, PropertyDefinition]`

**`CapabilitiesConfig`**:
- `timeseries`, `gnn`, `risk_scoring`, `rag_chat`, `explainability`, `structured_ingestion` (all `bool`, default `False`)

---

## medicare_fraud_cms_desynpuf — Entity Inventory

| Entity | Natural Key | Properties |
|--------|-------------|------------|
| `provider` | `[npi]` | `npi`, `entity_type_code`, `organization_name`, `last_name`, `first_name`, `primary_taxonomy_code`, `practice_state`, `practice_city`, `practice_postal_code`, `enumeration_date`, `deactivation_date` (11 properties total; expanded 2026-05-22) |
| `beneficiary` | `[hic_number]` | `hic_number`, `birth_date`, `sex_code`, `race_code`, `state_code` |
| `claim` | `[claim_id]` | `claim_id`, `service_date`, `through_date`, `amount` |
| `facility` | `[facility_id]` | `facility_id` |

## medicare_fraud_cms_desynpuf — Relationship Inventory

| Relationship | Source → Target |
|-------------|-----------------|
| `submitted_by` | `claim → provider` |
| `billed_for` | `claim → beneficiary` |
| `performed_at` | `claim → facility` |
| `referred_by` | `provider → provider` |

## medicare_fraud_cms_desynpuf — Feed Inventory (records.feeds)

| Feed name | Record type | Source | Maps to entities |
|-----------|------------|--------|-----------------|
| `beneficiary_2008` | `beneficiary_record` | `file_upload` | `beneficiary` |
| `beneficiary_2009` | `beneficiary_record` | `file_upload` | `beneficiary` |
| `beneficiary_2010` | `beneficiary_record` | `file_upload` | `beneficiary` |
| `carrier_claims_a` | `carrier_claim_record` | `file_upload` | `claim`, `beneficiary`, `provider`; relationships: `submitted_by`, `billed_for` |
| `carrier_claims_b` | `carrier_claim_record` | `file_upload` | `claim`, `beneficiary`, `provider`; relationships: `submitted_by`, `billed_for` |
| `inpatient_claims` | `inpatient_claim_record` | `file_upload` | `claim`, `beneficiary`, `provider`, `facility`; relationships: `submitted_by`, `billed_for`, `performed_at` [added 2026-05-22] |
| `outpatient_claims` | `outpatient_claim_record` | `file_upload` | `claim`, `beneficiary`, `provider`, `facility`; relationships: `submitted_by`, `billed_for`, `performed_at` [added 2026-05-22] |
| `pde` | `pde_record` | `file_upload` | `claim`, `beneficiary`; relationship: `billed_for` |
| `nppes_providers` | `nppes_provider_record` | `file_upload` | `provider` (NPPES-aligned 11 fields) [added 2026-05-22] |
