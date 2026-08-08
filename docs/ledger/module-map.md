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
Graph neural network analysis (link prediction, clustering). Adapters: `InMemoryGraphSnapshotSource`, `GraphRepositorySnapshotSource`.

**Snapshot reads are a full-graph read by design, and remain so.** The 5000-node cap truncates *after* reading everything, ranking by degree — which cannot be computed without every entity **and** every relationship. Entity reads are paged as of 2026-08-07 (a bounded result set per query rather than one query returning the whole knowledge base), but `get_relationships` has no paged variant and the degree map is O(n) regardless. Bounding this properly needs a degree-aware query that selects the top-N in the database; paging alone cannot do it, and this entry should not be read as claiming it does.

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

**Real-time delivery is SSE, and only SSE.** `AlertsCreatedEvent` (`alerts.created`, plural) is the produced event, published here and by `agent/coordinator.py`. A singular `AlertCreatedEvent` (`alert.created`) existed until 2026-08-07 documented as feeding a WebSocket alert stream; it was constructed nowhere, and `WebSocketHub.broadcast` had no production caller, so `/ws/alerts` and `/ws/pipeline` accepted connections and emitted nothing for their whole existence. Both routes, the hub, its auth guards, and four producerless event types (`alert.created`, `pipeline.progress`, `claims.received`, `claims.ingested`) were retired rather than given producers: the hub was process-local, so a broadcast would have reached only clients on the replica that consumed the event, whereas `/events/stream` rebuilds each snapshot from Postgres and is replica-safe by construction. `tests/capabilities/test_coherence.py` now fails if any declared event type has no producer.

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

**Long-lived responses participate in shutdown as of 2026-08-08.** `/events/stream` looped forever, breaking only on client disconnect, so uvicorn's graceful shutdown waited on it indefinitely — in dev a single open browser tab left the API container `unhealthy` and unresponsive after every `--reload`, recovering the moment the tab closed; in production the same shape stalls a deploy until the shutdown timeout. `create_app` now puts an `asyncio.Event` on `app.state.shutdown_event`, a lifespan sets it, and the stream's heartbeat *waits on* that event instead of sleeping blind, so shutdown is acted on immediately rather than up to a heartbeat later. Any future streaming route must do the same; `/events/stream` was the only unbounded one when this landed.

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

**Key exports:** `CapabilityRegistryService`, `CapabilityManifest`, `CapabilityExecutionEnvelope`, `create_default_capability_registry_service`, `register_executor`, `register_builtin_capability_executors`

**Adapters:** none — the registry is an in-process constructor, not persisted.

**Status:** `execute()` dispatches. The order is the security property — authorize, then dispatch, then audit — so a denied call never reaches the tool, and `CapabilityPermission.requires_audit` is no longer a flag nothing reads (denied and failed calls are audited too, since those are what a ledger is for).

`authorize()` **fails closed**. It previously read an omitted `domain_name` or `environment_tag` as "unrestricted", and an empty `required_roles` as "everyone" — the latter in two places, `_roles_can_access` (authorize) and `_role_can_access` (browse). All four are closed; the context arguments are required keyword arguments so omitting them is a type error rather than a silent bypass, and an empty permission list returns a distinct `no_roles_permitted` so a broken manifest is distinguishable from insufficient permission.

**Executors are bound separately from manifests.** A `Mapping -> Mapping` executor cannot reach a service, so the worker closes over its own instances and registers them at startup. `connector.sync.status` and `analytics.peer_context` are bound; the rest report `capability_not_executable`, which is truthful rather than a pretend success.

`CapabilityExecutor` takes an `ExecutionContext` — the actor, domain and environment `execute()` authorized against — so authorization context no longer rides inside the business payload. The context is frozen; an executor cannot edit the authorization it was handed.

**`rag.query` is unbound in the worker for a structural reason.** Its executor exists and is tested, but the RAG stack is assembled from bridges in `api/_rag_bridges` (embeddings → vectorstore → graph → LLM), and a worker import of `api.` would invert the module boundary. Moving those bridges somewhere both processes may import is the prerequisite. `evidence.checklist.generate` stays unbound by decision — writing a capability body is different work from making the engine run one.

**The browse API returns `executable` per capability**, sourced from `WORKER_EXECUTABLE_CAPABILITY_IDS` rather than the live registry. The executor map is module-level state *per process* and the API registers nothing, so reading its own registry made the API report every capability as unrunnable while the worker was running two. A test asserts the declaration matches what binding actually produces.

**Environment tags come from `shared/environments.py`**, the same vocabulary `CHILI_ENV` is validated against. They had drifted: manifests declared a `test` environment that never exists and omitted `local`, the default for the whole dev stack. Harmless while the gate passed on `None`; once it failed closed, every capability call under the dev stack would have denied.

---

## `connectors/` — Pull Connector Definitions

**Purpose:** Connector registration, sync-run records, and quarantine tracking for scheduled/manual pulls.

**Key exports:** `ConnectorService`, `ConnectorDefinition`, `ConnectorSyncRun`, `ConnectorRepositoryProtocol`, `ConnectorSourceAdapter`, `FilesystemSourceAdapter`, `handle_connector_page_queued`

**Adapters:** `InMemoryConnectorRepository`, `PostgresConnectorRepository` (`connectors`, `connector_sync_runs`, `connector_quarantine_records`, migration `0025`). Source adapters: `FilesystemSourceAdapter` only.

**Status:** sync runs execute. `start_sync` publishes `connector.page.queued`; `connectors/executor.py` reads one page from the source, registers its rows through **the same `RecordsService` the manual upload route uses** (so a pulled batch is indistinguishable downstream from an uploaded one — verified live: identical CSV via both paths produced identical `raw_records` and 57 identical graph nodes), advances `source_cursor`, then chains the next page or completes the run. Invalid rows are quarantined rather than dropped.

Idempotency is the run's own cursor: a page event whose cursor does not match `run.source_cursor` is skipped, and for the crash-between-persist-and-cursor case the records service reports the batch as a duplicate so counters and quarantine rows both hold still. `update_run` ignores a `None` cursor, so a run can never be moved backwards.

**Not implemented, and rejected rather than accepted-and-ignored:** the `object_store` and `http` source types, and the `interval`/`cron` schedule modes — nothing schedules connector runs at all. `IMPLEMENTED_SOURCE_TYPES`/`IMPLEMENTED_SCHEDULE_MODES` in `connectors/service.py` are the honest statement of what is honoured; registering anything else is a 422. Widen those sets when an adapter ships, not the `Literal`.

**Operational notes:** every filesystem path is confined to `CHILI_CONNECTOR_FS_ROOT` (default `/imports`, bind-mounted from `sample_data/connector_imports/` in the dev compose); the adapter has no unbounded mode. A `ConnectorSourceError` — path outside the root, missing directory, stale cursor — fails the run with the reason recorded, because no retry can fix it; anything else propagates for the worker's normal retry/DLQ handling. Page size is `CHILI_CONNECTOR_PAGE_LIMIT` (default 500).

`ConnectorSyncReconciler` fails runs that stop progressing, driven from the same worker tick and the same cutoff as the workflow and score-run sweeps. It re-reads each candidate before writing, so a page landing mid-sweep leaves the run alone. `queued` counts as well as `running` — a kickoff event lost before the first page leaves a run that never moves at all. The scan is served by `ix_connector_sync_runs_status_updated` (migration `0026`); the pre-existing index leads with `connector_id`, which a cross-KB sweep does not filter on.

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

**Status:** runs execute. `run_definition` publishes `workflow.step.queued` for the first step; `workflow_definitions/executor.py` resolves each step against the **published snapshot** named by the event's `definition_id`/`version` (so a definition edited mid-run cannot change a run already in flight), evaluates its condition, honours the approval gate, dispatches its capability, applies `on_failure`, then chains the next step or finishes the run. `condition`, `retry_policy` and `on_failure` are all evaluated.

**Authorization uses the run's recorded actor.** `run_definition` received `actor_user_id`/`actor_roles` and discarded them; the run now persists both, and a run without a recorded actor **fails** rather than dispatching. Inventing roles would bypass capability permissions for every workflow-dispatched call; passing none would deny everything and look like a broken capability.

**Conditions use a restricted grammar** (`conditions.py`): one comparison, `<step_id>.<key> <op> <literal>`, with no boolean operators, calls, indexing or attribute traversal. A condition is user-authored in a multi-tenant system, so there is no `eval`/`exec`/`compile` path anywhere in the module and a test asserts that at the source level. Conditions are validated when a definition is created — including references to unknown or *later* steps, which would otherwise always evaluate false and silently never run.

Idempotency is the step's own status: a step already COMPLETED, FAILED or SKIPPED returns before dispatch, so a redelivery cannot run a side-effecting capability twice. A retryable failure deliberately leaves the step PENDING, because a terminal status would make the requeued event skip itself.

The approval gate is server-side and fails closed. A parked run is `AWAITING_APPROVAL`, which is **not** terminal and is excluded from stale reconciliation (`RECONCILABLE_RUN_STATUSES`) — an approval left overnight is not a stalled run.

`POST /workflows/{run_id}/steps/{step_id}/approve` records the decision **and** republishes `workflow.step.queued`, which is what actually resumes the run: the executor's parking event was already acked, so recording the approval alone leaves the run exactly as stuck. The run is released to `QUEUED`, not `RUNNING` — the executor claims the step itself. `/reject` fails the run and requires a reason. Both require `admin` (platform RBAC is admin/analyst/service/viewer; "supervisor" is a *domain pack* role name), and the service refuses self-approval: a gate an actor can satisfy for their own run is not a gate.

**Remaining gaps:** The dashboard does not count or filter `awaiting_approval`, so a parked run is visible but not surfaced. And `BUILT_IN_WORKFLOW_CAPABILITIES` is now derived from the registry rather than hand-listed — it had named `playbook.step` and `human.approval`, which have no manifest.

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

**Adapters:** `InMemoryScoreRunRepository`, `PostgresScoreRunRepository` (`score_runs` + `score_batches`, migration `0024`)

**Status:** executes. `analytics/score_runs/executor.py` consumes `score.run.queued` (enumerate the KB's entities and create batches) and `score.batch.queued` (score one batch, then chain to the next or complete the run), dispatched through `execution/`. Run counters are summed from per-batch outcomes rather than incremented, so a replayed batch cannot double-count. `ScoreRunReconciler` fails runs that stop progressing, since a lost chain event would otherwise leave a run `running` forever.

**Worker death mid-batch is survivable.** `claim_batch` takes a reclaim window: a batch left `running` past `CHILI_SCORE_BATCH_STALE_SECONDS` (default 900) may be taken over by another worker when `reclaim_stale_pending` redelivers its event. Racing is safe — scoring is keyed on a deterministic request id, so two workers converge on the same rows — and `CHILI_SCORE_BATCH_MAX_ATTEMPTS` (default 5) stops a batch that kills its worker from being reclaimed forever, failing it so the run can still terminate.

`replay_failed_batches` publishes `score.batch.queued` for the first replayed batch. It previously published only `score_run.status_changed` — a notification the worker does not consume — so a replayed run was created with queued batches and executed nothing (live-confirmed 2026-08-07, fixed the same day).

**Enumeration is paged as of 2026-08-07** via `GraphRepository.get_entities_page(kb, *, limit, offset)`, page size `CHILI_SCORE_ENUMERATION_PAGE_SIZE` (default 1000). Verified live against Neo4j: 5,000 seeded entities enumerated exactly once each, no duplicates, no gaps; and a 57-entity KB at page size 7 across 9 pages. A full score run over HTTP reported `total_entities=57` against a graph holding exactly 57.

The honest limit: reads are bounded **per query**, but the id list is still accumulated in memory to form batches, so peak memory is still O(entities). Paging removes the single unbounded result set — the driver no longer buffers an entire knowledge base at once — not the accumulation.

**Skipped entities are counted separately as of 2026-08-08** (`skipped_entities` on run and batch, migration `0027`). Entities the risk service declines to score raise `RiskInsufficientSignalsError`, which the executor logs at INFO as an *expected* per-entity condition; they were previously counted as failures because `failed_entities` was computed as `len(entity_ids) - scored`. A live run over a KB whose entities carry fewer than two signals reported `completed, scored=0, failed=57` with no `error_message` anywhere — the reason existed only in worker logs. It now reports `skipped=57, failed=0`. `failed_entities` remains a remainder deliberately: anything neither scored nor skipped went missing in a way nothing anticipated, and that is a failure. Two unit tests encoded the old behaviour as intended (`..._count_as_failed_not_scored`); their real subject was "a skip must not inflate the scored count", which still holds.

---

## `tools/sample_data/` — Data Preparation CLI

**Purpose:** Filter and transform CMS source data for local development and demo.

**Tools:** `build_tennessee_subset.py` — filters NPPES (by state) and DE-SynPUF (cross-filtered by NPI) to a deterministic Tennessee subset. See `tooling-inventory.md`.

---

## `scripts/` — Shell Drivers

**Purpose:** Convenience scripts for local demo flows.

**Scripts:** `demo_ingest_tn_subset.sh` — drives `make demo-tn-subset`. `smoke_graph_workflow.sh` — end-to-end smoke test.
