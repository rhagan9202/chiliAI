# Module Map

**Generated:** 2026-05-22 (merge commit `acae4ac`)
**Reviewed:** 2026-07-26 against the current working tree — analytics adapter names corrected, agent handler entries updated, and post-snapshot modules (`cases/`, `conversations/`, `knowledgebases/`, `policy/`, `scorecards/`) added.
**Reviewed:** 2026-08-06 — the seven SAFE-CMS modules and three new `analytics/` submodules added below; the backend has **28 packages** (`ls backend/` is ground truth).

Each entry covers: purpose, primary public exports, adapters (if any), and forbidden/allowed dependencies per CLAUDE.md.

---

## `api/` — FastAPI Gateway

**Purpose:** HTTP + WebSocket entry point. Thin orchestration layer — routes requests to service modules, publishes events, pushes real-time updates. No business logic in routers.

**Key files:**
- `app.py` — `create_app()` factory
- `dependencies.py` — DI wiring for all services
- `state.py` — `ApiState` runtime app-state container assembled at startup
- `contracts.py` — API-facing request/response models
- `_kb_busy.py` — workflow/pending-cleanup mutation guard
- `_kb_projection.py` — KB read projection
- `_rag_bridges.py` — RAG ↔ KB document/entity bridges
- `_workflow_projection.py` — Worker-updated workflow lifecycle projection
- `middleware/` — auth (JWT/OIDC), RBAC (`require_role`), session store, policy registry, metrics, exceptions
- `routers/` — one file per resource group (see `http-routes.md`)

**Dependencies:** All service modules via DI. Must not contain business logic.

---

## `ingestion/` — Document Parsing & Entity Extraction

**Purpose:** Accepts raw documents (PDF, DOCX, TXT, JSON, CSV, XLSX), parses them, chunks text, extracts entities and relationships, and registers results for the pipeline.

**Key exports:** `IngestionService`, `IngestionServiceProtocol`

**Extractors:**
- `PatternDocumentExtractor` — Regex/heuristic baseline; used when no LLM client is injected.
- `LlmDocumentExtractor` — Schema-driven LLM extractor (added 2026-05-22). Derives prompts from `DomainConfig.entities/relationships`. Strips markdown fences, validates required properties, deduplicates entities by natural key within each chunk. Selected by `create_document_extractor` when an `LlmClientProtocol` is injected.

**Parsers (registered in `parsers/registry.py`):** PDF, DOCX, HTML, TXT, JSON, CSV, XLSX. The HTML parser currently emits normalized visible text; richer heading/link/table fidelity remains backlog work.

**Idempotency:** Content-hash `source_document_id` (SHA-256). Re-uploading the same bytes is a no-op. Changed content produces a new `source_document_id`; `DocumentUploadReceipt.replaced_document_id` points at the superseded entry.

**Provenance metadata emitted:** `source_kind="document"`, `source_document_id`, `source_chunk_id` on every `Entity` and `Relationship`.

**Forbidden dependencies:** `graph`, `analytics`, `api`

---

## `graph/` — Graph Database Access

**Purpose:** Knowledge graph CRUD, neighborhood queries, graph metrics.

**Key exports:** `GraphService`, `GraphServiceProtocol`

**Adapters:**
- `InMemoryGraphRepository` — ephemeral, process-local
- `Neo4jGraphRepository` — Neo4j 5.x with four idempotent schema statements (`_ensure_schema`)

**New in 2026-05-22:**
- `delete_by_source_document(kb_id, doc_id)` — removes all entities/relationships whose `source_document_id` matches `doc_id` within the KB. Used in re-upload cascade and document-level cleanup.
- Dual-graph reads: `get_entity`, `search_entities` accept `knowledge_base_ids: list[str]`.

**Forbidden dependencies:** `api`, `ingestion`, `analytics`

---

## `vectorstore/` — Vector Store Access

**Purpose:** Embedding storage and similarity search.

**Key exports:** `VectorService`, `VectorServiceProtocol`

**Adapters:**
- `InMemoryVectorStore`
- `QdrantVectorStore`

**Service contract (1.0):** `index`, `search`, `batch_search`, `get_record`, `count`, `delete_record`, `delete_knowledge_base`, `delete_by_source_document`

**New in 2026-05-22:** `delete_by_source_document(kb_id, doc_id)` — removes all indexed vectors whose metadata contains `source_document_id == doc_id`. Idempotent.

**Forbidden dependencies:** `api`, `ingestion`, `graph`

---

## `embeddings/` — Embedding Generation

**Purpose:** Text/graph-metric embedding generation.

**Key exports:** `EmbeddingsService`, `EmbeddingsServiceProtocol`

**Adapters:**
- `InMemoryEmbeddingsAdapter`
- `OpenAiEmbeddingsAdapter`
- `SentenceTransformersAdapter`

**Forbidden dependencies:** `api`, `graph`, `vectorstore`

---

## `rag/` — Retrieval-Augmented Generation Pipeline

**Purpose:** End-to-end RAG: query → embed → vector search → graph expand → assemble context → LLM → answer.

**Key exports:** `RagService`, `RagServiceProtocol`

**Adapter:** `InMemoryRagConversationStore` (conversation history)

**Dependencies:** `vectorstore` (protocol), `graph` (protocol), `llm` (protocol), `embeddings` (protocol)

**Forbidden dependencies:** `api`, `ingestion`, `analytics`

---

## `llm/` — LLM Client Abstraction

**Purpose:** Vendor-agnostic LLM client. Powers RAG answers and entity extraction.

**Key exports:** `LlmService`, `LlmServiceProtocol`, `create_llm_client` (factory)

**Adapters:**
- `InMemoryLlmClient` — deterministic stub (`provider="local"`)
- `OpenAiLlmClient` — OpenAI Chat Completions (`provider="openai"`, `[openai]` extra)
- `AnthropicLlmClient` — Anthropic Messages API (`provider="anthropic"`, `[anthropic]` extra)
- `OllamaLlmClient` — Self-hosted Ollama via OpenAI-compatible endpoint (`provider="ollama"`, `LlmConfig.base_url`) [added 2026-05-22]
- `FallbackLlmClient` — Decorator wrapping primary + ordered fallback list [added 2026-05-22]. Configured via `LlmConfig.fallback` (recursive). Built by `llm/factory.py::create_llm_client`.

**Note:** The TODO in `llm/service.py` mentioning "Add fallback model support" is resolved at the adapter/factory layer. The service itself remains unchanged.

**Forbidden dependencies:** Everything except `shared`

---

## `analytics/` — ML / AI Capability Modules

**Purpose:** Analytics pipelines triggered by worker events.

### `timeseries/`
Time-series anomaly detection. Adapters: `InMemoryTimeSeriesHistorySource`, `PostgresTimeSeriesHistorySource` (observation adapters live in `monitoring/adapters/postgres.py`).

### `gnn/`
Graph neural network analysis (link prediction, clustering). Adapter: `InMemoryGraphSnapshotSource`.

### `risk/`
Risk scoring. Adapters: `InMemoryRiskSignalSource`, `InMemoryRiskHistoryWriter`, `PostgresRiskHistoryStore` (writer-only + `load_historical_score`).

### `explainability/`
Evidence pack generation. Adapters: `InMemoryExplainabilityContextSource`, `ShapExplainabilityContextSource`.

### `peerstats/`
Peer-group statistics: aggregates record columns into peer baselines and persists derived risk signals. Adapters: `InMemoryRecordColumnSource`, `InMemoryDerivedRiskSignalWriter`, `PostgresRecordColumnSource`, `PostgresDerivedRiskSignalWriter`.

### `metrics/`
Entity-metric persistence (no service, no events). Adapters: `InMemoryEntityMetricRepository`, `PostgresEntityMetricRepository`. Throttled per-KB via `MetricsRecomputeThrottle`.

**Forbidden dependencies:** `api`, `ingestion`, other analytics sub-modules (cross-sub-module interaction via events only)

---

## `agent/` — Workflow Coordinator

**Purpose:** Pipeline worker. Consumes Redis Streams events, runs multi-step handlers, tracks lifecycle state.

**Entry point:** `python -m agent.coordinator`

**Pipeline handlers:**
- `handle_documents_uploaded` — document ingestion pipeline (parse → chunk → extract → upsert graph → embed → index)
- `handle_records_ingested` — maps raw records to entities/relationships → graph upsert + vector embed/index [enhanced 2026-05-22 to add embed+index step]; also runs best-effort policy/peerstats/timeseries stages and (analytics.34) an in-process Flow B analytics fan-out
- `handle_knowledge_base_deleted` — full 4-step retry cascade (graph → vector → raw_records → object_store) [added 2026-05-22]
- `handle_graph_updated_for_analytics` (Flow 2) — Flow B: GNN → risk → explainability → alerts.created, plus graph property write-back and throttled entity-metric persistence
- `handle_risk_scored_for_graph` (Flow 3) — risk score persistence + graph property snapshot
- `handle_alerts_created_for_graph` (Flow 4) — alert history persistence + graph property snapshot

**WorkflowRunStore adapters:** `InMemoryWorkflowRunStore`, `RedisWorkflowRunStore`. Selected by `CHILI_WORKFLOW_RUN_STORE_BACKEND`.

---

## `monitoring/` — Active Monitoring & Alert Generation

**Purpose:** Evaluates entity metrics against alert thresholds, generates and deduplicates alerts.

**Key exports:** `MonitoringService`, `MonitoringServiceProtocol`, `AlertsService`, `AlertsServiceProtocol`

**Adapters:** `InMemoryMonitoringAdapter`, `PostgresAlertHistoryStore` + observation adapters

---

## `shared/` — Lightweight Shared Contracts

**Purpose:** Generic platform types, cross-cutting protocols, and small utilities. Must remain dependency-light. No business logic.

**Key exports:** `Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`, `EntityDefinition` (with `natural_key: list[str]` added 2026-05-22), `RelationshipDefinition`

**New in 2026-05-22:** `shared/provenance.py` — canonical metadata-key constants used by records mappers, document validator, graph + vector cascade-delete, and the coordinator.

**Forbidden dependencies:** Everything — must be leaf dependency

---

## `config/` — Domain Configuration

**Purpose:** Load and validate domain YAML/JSON config into `DomainConfig`.

**Key exports:** `DomainConfig`, `load_config`

**Config files:** `defaults/medicare_fraud.yaml`, `defaults/medicare_fraud_cms_desynpuf.yaml`, `defaults/food_supply_chain.yaml`, `defaults/department_air_force_housing.yaml`; `overlays/medicare_fraud_dev.yaml` (dev overlay over `defaults/medicare_fraud.yaml`, applied via `CHILI_CONFIG_OVERLAY_PATH` — ADR 0001, `overlay.py`, BL-044)

**New in 2026-05-22:**
- `LlmConfig.provider` gains `"ollama"` literal
- `LlmConfig.base_url` (custom endpoint)
- `LlmConfig.fallback: LlmConfig | None` (recursive fallback chain)
- `EntityDefinition.natural_key: list[str]` (populated in `medicare_fraud_cms_desynpuf.yaml`)

**Forbidden dependencies:** Everything except `shared`

---

## `events/` — Event Bus Abstraction

**Purpose:** Redis Streams event transport abstraction.

**Key exports:** `EventBus` (protocol), `AnyEvent`, all event types in `types.py`

**Adapters:** `InMemoryEventBus`, `RedisStreamsEventBus`

---

## `storage/` — Object Storage Abstraction

**Purpose:** Raw document and artifact persistence.

**Key exports:** `ObjectStore` (protocol)

**Adapters:** `InMemoryObjectStore`, `LocalFsObjectStore`, `S3ObjectStore` (also serves MinIO)

---

## `database/` — Postgres + TimescaleDB Connection Provider

**Purpose:** Connection pooling and schema migrations (Alembic).

**Key exports:** `ConnectionProvider` (protocol), `DatabaseConnection`, `DatabaseCursor`

**Adapters:** `PsycopgConnectionProvider` (psycopg 3 pool), `InMemoryConnectionProvider` (tests)

---

## `records/` — Structured / Tabular Ingestion

**Purpose:** Accepts CSV/JSONL/api-push feeds, validates against config-declared feed schema, lands rows in `raw_records`, publishes `RecordsIngestedEvent`.

**Key exports:** `RecordsService`, `RecordsServiceProtocol`

**Adapters:** `InMemoryRawRecordStore`, `PostgresRawRecordStore`

**New in 2026-05-22:** `delete_by_kb(kb_id)` on `RawRecordStore` protocol and both adapters. This is the raw-records leg of the KB delete cascade.

---

## `cases/` — Investigation Case Management

**Purpose:** Durable, KB-scoped investigation cases (BL-010). Cases are promoted from alerts (capturing the originating alert, its evidence pack, and a timeline snapshot) and persisted across the API and worker containers.

**Key exports:** `CaseService`, `CaseRepository` (protocol: `create / get / list / update / delete_by_kb`)

**Adapters:** `InMemoryCaseRepository`, `PostgresCaseRepository`

---

## `conversations/` — RAG Chat Conversation Persistence

**Purpose:** Durable RAG chat conversations and message history, including assistant-message citations (BL-012). Shared across API and worker containers.

**Key exports:** `ConversationService`, `ConversationRepository` (protocol: `create / get / save`)

**Adapters:** `InMemoryConversationRepository`, `PostgresConversationRepository`

---

## `knowledgebases/` — KB & Document Metadata

**Purpose:** Knowledge base and document metadata persistence, so `api/` and `agent/` can share KB state without importing from each other. Also owns the centralized KB delete cascade (`cleanup.py`: `KbDeletionStores`, `kb_deletion_steps`, `delete_object_store_prefix`).

**Key exports:** `KnowledgeBaseRepository` (protocol), `cleanup.py` cascade helpers, `snapshots.py`

**Adapters:** `InMemoryKnowledgeBaseRepository`, `ObjectStoreKnowledgeBaseRepository`

---

## `policy/` — Policy Intelligence

**Purpose:** Durable, KB-scoped policy intelligence (BL-011). Rule packs from `DomainConfig.policy_rules` are evaluated (`evaluation.py`, pure `evaluate()` — no I/O) against freshly stored entities and throttled graph metrics; each match upserts a persisted `PolicyItem` that analysts triage (accept / reject / defer / escalate-to-case). Disposed items never reopen (natural key `(kb_id, rule_id, target_ref)`).

**Key exports:** `PolicyService`, `evaluate()`, `PolicyItemRepository` (protocol: `upsert / get / list / update / delete_by_kb`)

**Adapters:** `InMemoryPolicyItemRepository`, `PostgresPolicyItemRepository`

---

## `scorecards/` — Housing Scorecard Runs

**Purpose:** Durable scorecard run generation for the Air Force housing pack. Evaluates config-declared templates (`DomainConfig.scorecards`) over the KB's ingested feed records, persists runs with per-metric health/completeness/citations, and stores JSON/Markdown export payloads.

**Key exports:** `ScorecardService`, `create_scorecard_service`, `ScorecardSourceRecordLoader` (protocol), `ScorecardRunRepository` (protocol)

**Adapters:** `InMemoryScorecardRunRepository`, `PostgresScorecardRunRepository`

---

## SAFE-CMS surge modules (added 2026-08-02 → 08-05)

Seven top-level packages and three `analytics/` submodules landed during the
surge and were absent from this map until 2026-08-06. Implementation depth
varies sharply — the notes record what is actually wired, because several of
these expose an API whose work nothing executes.

## `auditlog/` — Append-Only Material-Action Ledger

**Purpose:** Records material analyst/system actions (auth, KB lifecycle, alert triage, case mutations, explanation reviews, workflow-definition lifecycle, identity decisions). Writes are non-blocking; failures land in a bounded in-process buffer surfaced at `GET /audit/status`.

**Key exports:** `AuditLogService`, `AuditEvent`, `AuditEventCreate`, `AuditEventQuery`, `AuditLogRepository` (protocol), `PLATFORM_TENANT_ID`

**Adapters:** `InMemoryAuditLogRepository`, `PostgresAuditLogRepository` (`audit_log`, migration `0016`)

**Tenancy:** every event is written under the single `PLATFORM_TENANT_ID`; KB scoping uses `knowledge_base_id`. `tenant_id` is never accepted from a request body.

---

## `capabilities/` — Typed Capability / Tool Registry

**Purpose:** Catalog of capabilities available to workflows and agents, with input/output schemas, role/domain/environment permissions, side-effect class, and execution envelopes.

**Key exports:** `CapabilityRegistryService`, `CapabilityManifest`, `CapabilityExecutionEnvelope`, `create_default_capability_registry_service`

**Adapters:** none — the registry is an in-process constructor, not persisted.

**Status:** browse + `authorize()` are real; there is **no dispatcher**. Nothing executes a capability through this registry in production.

---

## `connectors/` — Pull Connector Definitions

**Purpose:** Connector registration, sync-run records, and quarantine tracking for scheduled/manual pulls.

**Key exports:** `ConnectorService`, `ConnectorDefinition`, `ConnectorSyncRun`, `ConnectorRepositoryProtocol`

**Adapters:** `InMemoryConnectorRepository` only — **no Postgres adapter and no migration**, so definitions and runs are process-lifetime.

**Status:** metadata only. No source adapter, no scheduler, no ingestion events, no replay. `start_sync` writes a `queued` row nothing advances.

---

## `governance/` — Release Readiness & Eval Runs

**Purpose:** Release-readiness reporting over playbooks, workflow definitions and explanation reviews, plus a durable eval-run lifecycle with baseline approval.

**Key exports:** `GovernanceReportService`, `GovernanceEvalService`, `GovernanceEvalRepository` (protocol)

**Adapters:** `InMemoryGovernanceEvalRepository`, `PostgresGovernanceEvalRepository` (`governance_eval_runs`, migrations `0022`/`0023`)

**Status:** `has_approved_eval` is an enforced gate on playbook publish (409 without an approved baseline). Metrics are caller-supplied — there is no eval runner that scores data.

---

## `playbooks/` — Versioned Fraud Playbooks

**Purpose:** Config-authored seed playbooks published as immutable DB snapshots, with export/import as domain-pack artifacts.

**Key exports:** `PlaybookService`, `PlaybookSnapshot`, `PlaybookRepository` (protocol)

**Adapters:** `InMemoryPlaybookRepository`, `PostgresPlaybookRepository` (`fraud_playbook_snapshots`, migrations `0019`/`0020`)

---

## `readiness/` — KB / Domain Readiness Aggregation

**Purpose:** Aggregates readiness for the app-shell workspace control.

**Key exports:** `ReadinessService`, `ReadinessReport`, `ReadinessIssue`

**Adapters:** none.

**Status:** probes four components (`knowledge_base`, `connectors`, `workflows`, `capabilities`) — **not** graph, vector, embeddings or analytics freshness. Its `no_connectors`/`no_workflows` blockers make a fully ingested KB report `ready: false`.

---

## `workflow_definitions/` — User-Authored Workflow Definitions

**Purpose:** Definition CRUD, static validation against the capability registry, approval/retire lifecycle, and idempotent run handoff.

**Key exports:** `WorkflowDefinitionService`, `WorkflowDefinition`, `WorkflowStepDefinition`, `WorkflowDefinitionRepository` (protocol)

**Adapters:** `InMemoryWorkflowDefinitionRepository`, `PostgresWorkflowDefinitionRepository` (`workflow_definition_snapshots`, migration `0021`)

**Status:** `run_definition` persists a `QUEUED` `WorkflowRun` and audits the request. **No executor** — no event is published and no worker consumes it, so steps never run. `condition`, `retry_policy`, `on_failure` are stored but never evaluated.

---

## `analytics/features/` — Feature Catalog

**Purpose:** Reads the domain pack's versioned typology/feature catalog.

**Key exports:** `FeatureCatalogService`, `create_feature_catalog_service`

**Status:** catalog metadata is real; `list_entity_values` is a stub returning `[]`, and no durable feature-value store exists.

---

## `analytics/identity_resolution/` — Canonical Identity Links

**Purpose:** Deterministic identity scoring, canonical link records, and audited steward merge/split decisions.

**Key exports:** `IdentityDecisionService`, `IdentityLinkRecord`, `IdentityLinkRepository` (protocol)

**Adapters:** `InMemoryIdentityLinkRepository`, `PostgresIdentityLinkRepository` (`identity_links`, migration `0018`)

**Status:** no production path **creates** a link — `upsert_link`'s only non-test caller requires the link to exist already. `IdentityLinkDecisionRecordedEvent` is published with no consumer.

---

## `analytics/score_runs/` — Score-All Run Lifecycle

**Purpose:** KB-scoped score-all run/batch state with idempotency keys, cancel and replay.

**Key exports:** `ScoreRunService`, `ScoreRun`, `ScoreRunRepositoryProtocol`

**Adapters:** `InMemoryScoreRunRepository` only — **no Postgres adapter and no migration**, so runs do not survive a restart.

**Status:** state machine only. Nothing executes batches; `ScoreRunStatusChangedEvent` has no consumer.

---

## `tools/sample_data/` — Data Preparation CLI

**Purpose:** Filter and transform CMS source data for local development and demo.

**Tools:** `build_tennessee_subset.py` — filters NPPES (by state) and DE-SynPUF (cross-filtered by NPI) to a deterministic Tennessee subset. See `tooling-inventory.md`.

---

## `scripts/` — Shell Drivers

**Purpose:** Convenience scripts for local demo flows.

**Scripts:** `demo_ingest_tn_subset.sh` — drives `make demo-tn-subset`. `smoke_graph_workflow.sh` — end-to-end smoke test.
