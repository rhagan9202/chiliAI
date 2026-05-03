# Story Prompt Audit — 2026-04-29

## Scope

Audited all 135 files in `docs/planning/story_prompts/` against the current repository state, backlog status, visible TODOs, and checklist state.

## Executive Summary

| Status | Count | Stories |
|--------|------:|---------|
| Complete | 17 | E1-S01 through E1-S10, E2-S01 through E2-S06, E3-S01 |
| Partial | 0 | None identified |
| Unstarted | 118 | E3-S02 through E21-S02, except E3-S01 |
| Prompt drift corrected | 6 files | E3-S02, E3-S03, E3-S04, E3-S05, E17-S01, E21-S02 |

## Checklist Audit Result

- Complete stories already had all Done Checklist items checked and matched implementation evidence.
- Unstarted stories already had Done Checklist items unchecked and remain open.
- No story had a mixed checked/unchecked completion checklist after audit.
- No checklist checkbox state changes were required.
- Prompt text drift was corrected where references no longer matched the codebase.

## Epic Checklist Summary

| Epic | Stories | Complete | Partial | Unstarted |
|------|--------:|---------:|--------:|----------:|
| E1 | 10 | 10 | 0 | 0 |
| E2 | 6 | 6 | 0 | 0 |
| E3 | 8 | 1 | 0 | 7 |
| E4 | 8 | 0 | 0 | 8 |
| E5 | 14 | 0 | 0 | 14 |
| E6 | 8 | 0 | 0 | 8 |
| E7 | 12 | 0 | 0 | 12 |
| E8 | 8 | 0 | 0 | 8 |
| E9 | 13 | 0 | 0 | 13 |
| E10 | 15 | 0 | 0 | 15 |
| E11 | 5 | 0 | 0 | 5 |
| E12 | 3 | 0 | 0 | 3 |
| E13 | 2 | 0 | 0 | 2 |
| E14 | 2 | 0 | 0 | 2 |
| E15 | 3 | 0 | 0 | 3 |
| E16 | 4 | 0 | 0 | 4 |
| E17 | 4 | 0 | 0 | 4 |
| E18 | 2 | 0 | 0 | 2 |
| E19 | 2 | 0 | 0 | 2 |
| E20 | 4 | 0 | 0 | 4 |
| E21 | 2 | 0 | 0 | 2 |
| Total | 135 | 17 | 0 | 118 |

## Completed Stories Verified

- E1-S01: Add audit and versioning fields to Entity
- E1-S02: Add audit and versioning fields to Relationship
- E1-S03: Consolidate `_utc_now()` into `shared/utils.py`
- E1-S04: Add graph database configuration section to DomainConfig
- E1-S05: Add vector store configuration section to DomainConfig
- E1-S06: Add LLM, embeddings, storage, events, monitoring, and RAG configuration sections to DomainConfig
- E1-S07: Config-driven adapter selection in the DI layer
- E1-S08: Enrich event envelope with correlation_id, source, and schema_version
- E1-S09: Add updated_at and status enrichment to KnowledgeBase
- E1-S10: Enrich EvidencePack and Alert lifecycle fields
- E2-S01: Extend GraphRepository protocol with read/query methods
- E2-S02: Implement read/query methods on InMemoryGraphRepository
- E2-S03: Add GraphService read/query methods and service models
- E2-S04: Add Neo4j production adapter
- E2-S05: Add transaction semantics to graph upserts
- E2-S06: Add batch chunking for graph upserts
- E3-S01: Qdrant Vector Store Adapter

## Newly Discovered Discrepancies and Drift

The following prompt text drift was found and corrected:

1. E3-S02 and E3-S03 referenced `EmbeddingsConfig.model_name`; the current schema uses `EmbeddingsConfig.model`.
2. E3-S04 and E3-S05 referenced `LlmConfig.model_name`; the current schema uses `LlmConfig.model`.
3. E17-S01 referenced a future `AlertingConfig`; the current schema uses `AlertsConfig`.
4. E21-S02 was titled and scoped around `AlertingConfig`; the current schema uses `AlertsConfig`, with `MonitoringConfig` also already carrying related monitoring cadence and limit fields.

No completed story was found to have a stale checked checklist or an unmet completion gate.

## Missed Completion Gates

All missed completion gates are concentrated in unstarted stories. The recurring open gates are:

- Acceptance criteria not implemented.
- Target files not created or modified.
- Tests not written or not run for the story scope.
- Required coverage gate not established for the affected module.
- Lint gate not run for the story scope.
- Type-safety gate not run for the story scope.

Additional high-impact missed steps:

- E3 production adapters remain mostly unstarted, blocking production embeddings, LLM, and object storage paths.
- E4 pipeline continuation after graph updates remains unstarted, blocking embeddings, vector indexing, and final KB-ready lifecycle completion.
- E5 API router expansion remains unstarted, leaving most frontend-facing contracts absent.
- E6 RAG production flow remains unstarted because embeddings, vector retrieval, graph expansion, and LLM generation adapters are not wired.
- E7 analytics suite remains unstarted, including timeseries, GNN, risk scoring, explainability, and analytics coordinator integration.
- E8 monitoring and alerting behavior remains unstarted beyond foundational shared/config models.
- E9 frontend application remains unstarted; the React app is still scaffold-level.
- E10 operational hardening remains unstarted, including CI, auth, RBAC, logging, metrics, Kubernetes, E2E, tracing, and dependency scanning.
- E11 through E21 hardening stories remain unstarted, even where scaffolding or TODO comments exist.

## Unstarted Stories

### E3 — Production Adapters

- E3-S02: Sentence-Transformers Embeddings Adapter
- E3-S03: OpenAI Embeddings Adapter
- E3-S04: OpenAI LLM Adapter
- E3-S05: Anthropic LLM Adapter
- E3-S06: S3/MinIO Object Storage Adapter
- E3-S07: Local Filesystem Object Storage Adapter
- E3-S08: Extend ObjectStore Protocol with delete, exists, list_keys

### E4 — Pipeline Completion

- E4-S01: Wire embeddings step after graph.updated
- E4-S02: Wire vector indexing step after embeddings.complete
- E4-S03: Emit kb.ready event at pipeline completion
- E4-S04: Dead-letter queue handling for failed pipeline events
- E4-S05: Retry count tracking with exponential backoff
- E4-S06: Graceful shutdown for the worker process
- E4-S07: Worker health check endpoint
- E4-S08: Config-driven adapter wiring in the worker coordinator

### E5 — API Routers

- E5-S01: Alerts router — list alerts
- E5-S02: Alerts router — acknowledge and resolve alerts
- E5-S03: Investigation router — entity detail and neighborhood query
- E5-S04: Investigation router — search entities
- E5-S05: RAG chat router — send message
- E5-S06: RAG chat router — streaming response via SSE
- E5-S07: WebSocket hub — real-time alerts
- E5-S08: WebSocket hub — pipeline status
- E5-S09: Analytics router — risk scores and timeseries
- E5-S10: Analytics router — GNN cluster results
- E5-S11: Knowledge base router — create and list KBs
- E5-S12: Knowledge base router — get and delete KB
- E5-S13: Knowledge base router — list and delete documents within a KB
- E5-S14: Register all new routers in the app factory

### E6 — RAG Pipeline

- E6-S01: Production QueryEmbedder adapter — delegate to EmbeddingsService
- E6-S02: Production ContextRetriever adapter — delegate to VectorStoreService
- E6-S03: Production GraphContextExpander adapter — delegate to GraphService
- E6-S04: Production AnswerGenerator adapter — delegate to LLMService
- E6-S05: Domain-configurable RAG system prompt
- E6-S06: Streaming RAG response support
- E6-S07: Citation formatting with source references
- E6-S08: RAG module test suite — achieve >= 85% coverage

### E7 — Analytics Suite

- E7-S01: Timeseries — Seasonal Decomposition Anomaly Detection
- E7-S02: Timeseries — Isolation Forest Anomaly Detection
- E7-S03: Timeseries — Sliding Window Continuous Analysis
- E7-S04: GNN — Community Detection (Louvain)
- E7-S05: GNN — Node Embedding Export
- E7-S06: Risk Scoring — Ensemble Model with Configurable Strategies
- E7-S07: Risk Scoring — Temporal Trend Comparison
- E7-S08: Explainability — Structured Narrative Generation
- E7-S09: Explainability — SHAP/LIME Feature Attribution Adapter
- E7-S10: Wire Analytics into the Coordinator Event Chain
- E7-S11: Self-Reinforcing Loop — Write Risk Scores Back to Graph
- E7-S12: Analytics Module Test Coverage — Achieve >= 85% Per Sub-Module

### E8 — Monitoring & Alerting

- E8-S01: Time-window aggregation for monitoring evaluation
- E8-S02: Alert deduplication within configurable window
- E8-S03: Alert suppression rules and maintenance windows
- E8-S04: Alert rate limiting
- E8-S05: Alert lifecycle state machine
- E8-S06: Alert grouping and correlation
- E8-S07: Monitoring stream consumer — continuous evaluation
- E8-S08: Monitoring module test suite — achieve >= 85% coverage

### E9 — Frontend Application

- E9-S01: App shell, routing, and layout scaffold
- E9-S02: Domain config fetching and context provider
- E9-S03: TanStack Query integration and API client setup
- E9-S04: Zustand client state setup
- E9-S05: Dashboard page
- E9-S06: Knowledge Base Manager page — list and create
- E9-S07: Knowledge Base Manager — document upload and delete
- E9-S08: Alert Feed page
- E9-S09: Configuration Editor page
- E9-S10: Investigation Workbench — graph visualization
- E9-S11: Investigation Workbench — entity detail and evidence panels
- E9-S12: WebSocket hook for real-time updates
- E9-S13: RAG Chat page

### E10 — Quality, Security & Operations

- E10-S01: GitHub Actions CI pipeline — lint, typecheck, test, build
- E10-S02: Backend test coverage gap closure — LLM module
- E10-S03: Backend test coverage gap closure — config module
- E10-S04: Backend test coverage gap closure — graph module
- E10-S05: Backend test coverage gap closure — storage module
- E10-S06: Auth middleware — JWT/OIDC authentication
- E10-S07: RBAC authorization — role-based access control
- E10-S08: Structured logging with structlog
- E10-S09: Prometheus metrics endpoint
- E10-S10: Input validation hardening
- E10-S11: Kubernetes manifests and Helm chart
- E10-S12: TLS/HTTPS and secrets management
- E10-S13: E2E integration test suite
- E10-S14: OpenTelemetry distributed tracing
- E10-S15: Security audit checklist and dependency scanning

### E11 — Config System Hardening

- E11-S01: Config overlay/merging — env-specific overrides and secrets resolution
- E11-S02: Config hot-reload — file watcher and API-triggered reload
- E11-S03: Config management API endpoints
- E11-S04: CORS origins from config or ALLOWED_ORIGINS env var
- E11-S05: API health check — subsystem liveness + Kubernetes readiness endpoint

### E12 — Ingestion Hardening

- E12-S01: Ingestion document idempotency via content-hash deduplication
- E12-S02: LlmDocumentExtractor — LLM-backed entity and relationship extraction
- E12-S03: Extraction confidence threshold filtering in DocumentResultValidator

### E13 — LLM Adapter Protocol Extensions

- E13-S01: LLM adapter protocol extension — streaming, batch, and token counting
- E13-S02: LLM service hardening — retry, fallback model, and token budget

### E14 — Embeddings Service & Protocol Extensions

- E14-S01: Embedder protocol — model introspection, health check, async variant
- E14-S02: EmbeddingsService — graph-metric hybrid embedding flow

### E15 — RAG Service Hardening

- E15-S01: RAG service hardening — retry, circuit breaker, and graceful degradation
- E15-S02: ContextRetriever protocol — min_score threshold, pagination, and hybrid search
- E15-S03: GraphContextExpander — configurable depth, entity type filters, and timeout

### E16 — Agent Lifecycle & Idempotency

- E16-S01: AgentServiceProtocol — workflow lifecycle methods (get_status, list, cancel)
- E16-S02: WorkflowRunStoreProtocol — list, delete, update + in-memory implementation
- E16-S03: Agent service idempotency key and compensating transaction
- E16-S04: Coordinator per-event error isolation

### E17 — Shared Type & Protocol Hardening

- E17-S01: SeverityLevel enum to replace bare str on Alert
- E17-S02: Alert enrichment — owner, tags, and domain_config_version
- E17-S03: Shared cross-cutting protocols — HealthCheckable, Lifecycle, Measurable
- E17-S04: Shared utilities — json_serialize, retry decorator, truncate_text

### E18 — VectorStore Protocol & Service Completions

- E18-S01: VectorStoreProtocol — delete, get_record, count, and batch_search
- E18-S02: VectorStoreService — KB delete flow, batch size limits, and audit persistence

### E19 — Event Bus Reliability

- E19-S01: InMemory event bus — consumer groups and pending message state
- E19-S02: EventCodec auto-discovery and schema_version support

### E20 — Analytics Adapter Protocol Completions

- E20-S01: Timeseries adapter protocol — batch analysis and date-range filtering
- E20-S02: Explainability adapter protocol — batch loading and rich context queries
- E20-S03: GNN adapter protocol — incremental graph loading and streaming inference
- E20-S04: Risk adapter protocol — batch score loading and real-time signal streaming

### E21 — Graph & Alerting Config Completions

- E21-S01: InMemoryGraphRepository — referential integrity checks
- E21-S02: AlertsConfig schema extension — dedup window, max alerts, severity levels

## Recommended Next Story Order

1. E3-S02 or E3-S03: unblock embeddings.
2. E3-S08, then E3-S06 or E3-S07: unblock object storage lifecycle needs.
3. E3-S04 or E3-S05: unblock production RAG generation.
4. E4-S01 through E4-S03: complete the worker pipeline after graph updates.
5. E5-S11 through E5-S14: expose core KB contracts before frontend work.
