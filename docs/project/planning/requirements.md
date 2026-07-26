# chiliAI Product Requirements

> Canonical product scope owned by the Requirements Gatherer agent.
> Version: 1.2 · Last updated: 2026-07-12 (config-management write surface + scorecards/housing refresh; BL-038/BL-039 requirement families added)

## 1. Product Vision

chiliAI is a **domain-reconfigurable Graph RAG analytics platform** that combines knowledge-graph construction, vector-based retrieval-augmented generation, graph neural networks, time-series analysis, anomaly detection, configuration-driven statutory/metric scorecards, and explainable AI into a single, loosely coupled system. A single YAML/JSON configuration ("domain pack") retargets the entire application to different investigation and oversight domains (Medicare fraud, food supply chain, military housing oversight, etc.) without code changes — including switching the active domain on a running deployment. Analysts and oversight executives build knowledge bases, monitor live data streams, surface alerts with evidence, explore entity graphs, grade domains against configured statutory scorecards, and converse with the knowledge through an LLM-powered interface — all within a rich browser-based workbench.

## 2. Target Users & Domains

- **Primary users:** Fraud investigators, compliance analysts, supply-chain auditors, intelligence analysts, and program-oversight executives working on entity-and-relationship-centric investigations and statutory-reporting oversight.
- **Supported domains (exemplars):** Medicare fraud detection (initial exemplar), food supply chain monitoring, Department of the Air Force housing oversight (third shipped domain), financial crime, and any domain requiring entity graph construction, RAG retrieval, anomaly detection, evidence-driven investigation, or configured metric scorecards. Adding a new domain requires only a configuration change, not application code changes.

## 3. Functional Requirements

### 3.1 Knowledge Base Management

- **REQ-KB-001** — The system shall allow users to create, list, detail, and delete knowledge bases, each isolated by a unique `knowledge_base_id`.
- **REQ-KB-002** — The system shall allow users to upload documents (PDF, DOCX, HTML, JSON, TXT) to a knowledge base and track document status (pending, processing, indexed, failed).
- **REQ-KB-003** — The system shall parse uploaded documents, extract text chunks, identify entities and relationships per the domain configuration, and integrate them into the knowledge base's graph and vector store.
- **REQ-KB-004** — The system shall provide a document inventory view per knowledge base showing document count, ingestion status, and processing timestamps.
- **REQ-KB-005** — The system shall allow users to remove documents from a knowledge base and clean up associated graph nodes, embeddings, and object-store artifacts.
- **REQ-KB-006** — The system shall persist knowledge base metadata (name, description, creation timestamp, document count, entity count, relationship count) in a durable repository accessible across API and worker containers.
- **REQ-KB-007** — The system shall support point-in-time knowledge base snapshots and restoration for disaster recovery.

### 3.2 Structured Record Ingestion

- **REQ-REC-001** — The system shall accept structured records (CSV, JSONL) via file upload or API push to a knowledge base.
- **REQ-REC-002** — The system shall validate incoming records against domain-configured feed schemas (field names, types, constraints).
- **REQ-REC-003** — The system shall land canonical validated records in a durable `raw_records` table for audit and reprocessing.
- **REQ-REC-004** — The system shall publish a `RecordsIngestedEvent` to trigger downstream entity normalization and graph integration workflows.

### 3.3 Graph & Entity Exploration

- **REQ-GRAPH-001** — The system shall persist entities and relationships in a pluggable graph database (in-memory, Neo4j, and future adapters).
- **REQ-GRAPH-002** — The system shall scope all graph queries by `knowledge_base_id` at the protocol boundary to enforce isolation.
- **REQ-GRAPH-003** — The system shall provide entity search by type, property filters, and natural key, returning matching entities with summary metadata.
- **REQ-GRAPH-004** — The system shall provide entity detail views showing all properties, related entities, computed metrics, and risk scores.
- **REQ-GRAPH-005** — The system shall provide entity neighborhood expansion, allowing users to traverse relationships up to a configurable depth.
- **REQ-GRAPH-006** — The system shall support graph backup and restore procedures as part of disaster recovery capabilities.

### 3.4 Vector Store & Embeddings

- **REQ-VEC-001** — The system shall generate embeddings for document chunks, entity descriptions, and relationship contexts using a pluggable embedder (in-memory, OpenAI, sentence-transformers).
- **REQ-VEC-002** — The system shall store embeddings in a pluggable vector store (in-memory, Qdrant, and future adapters).
- **REQ-VEC-003** — The system shall support similarity search over embeddings with configurable top-k and distance threshold.
- **REQ-VEC-004** — The system shall filter vector search results by `knowledge_base_id` and optional entity-type constraints.

### 3.5 RAG Chat Interface

- **REQ-RAG-001** — The system shall provide a conversational RAG interface allowing users to query a selected knowledge base in natural language.
- **REQ-RAG-002** — The system shall embed the user query, retrieve relevant chunks from the vector store, expand retrieved entities via the graph, assemble context, and generate an LLM-powered answer.
- **REQ-RAG-003** — The system shall cite retrieved chunks and entities as provenance for the generated answer.
- **REQ-RAG-004** — The system shall support pluggable LLM backends (in-memory, OpenAI, Anthropic, Ollama, vLLM) with fallback chains for high availability.

### 3.6 Analytics & Monitoring

- **REQ-ANALYTICS-001** — The system shall compute entity-level metrics (degree, betweenness, clustering coefficient) and persist them in a time-series hypertable.
- **REQ-ANALYTICS-002** — The system shall run time-series anomaly detection over entity metrics and flag outliers per domain-configured thresholds.
- **REQ-ANALYTICS-003** — The system shall execute graph neural network link prediction and clustering to surface hidden relationships and entity communities.
- **REQ-ANALYTICS-004** — The system shall compute risk scores for entities using configurable scoring strategies and persist score history.
- **REQ-ANALYTICS-005** — The system shall generate alerts with severity levels (low, medium, high, critical) and attach evidence packs (subgraph patterns, metrics, reasoning).
- **REQ-ANALYTICS-006** — The system shall persist alert history in a time-series table for audit and trend analysis.
- **REQ-ANALYTICS-007** — The system shall snapshot current risk scores, alert counts, and assessment timestamps onto graph entities for fast lookup.

### 3.7 Alert Feed & Investigation

- **REQ-ALERT-001** — The system shall provide a real-time alert feed with filtering by severity, status (open, acknowledged, closed), and knowledge base.
- **REQ-ALERT-002** — The system shall allow users to acknowledge and close alerts, persisting status changes.
- **REQ-ALERT-003** — The system shall surface evidence packs attached to alerts, showing the subgraph, metrics, and reasoning that triggered the alert.
- **REQ-ALERT-004** — The system shall allow users to promote alerts to investigation cases with associated evidence packs and entity timelines.

### 3.8 Workflow Orchestration

- **REQ-WORKFLOW-001** — The system shall orchestrate multi-step pipelines (ingestion → extraction → graph build → embedding → analytics → alerting) through an event-driven workflow coordinator consuming Redis Streams.
- **REQ-WORKFLOW-002** — The system shall track workflow run lifecycle (pending, running, completed, failed) in shared state accessible to both API and worker containers.
- **REQ-WORKFLOW-003** — The system shall provide a workflow run history view showing status, steps executed, duration, and failure reasons.
- **REQ-WORKFLOW-004** — The system shall route failed events to a dead-letter queue for manual replay and support graceful shutdown with in-flight event checkpointing.
- **REQ-WORKFLOW-005** — The system shall support event replay from persistent Redis Streams log for disaster recovery.

### 3.9 Domain Configuration & Configuration Management

- **REQ-CONFIG-001** *(amended v1.2; pack inventory updated 2026-07-15 per BL-044/config.04)* — The system shall load a single YAML/JSON domain configuration ("domain pack") defining entity types, relationship types, property schemas, display labels, records feed schemas, policy rule packs, scorecard templates, thresholds, UI navigation/labels, infra backend selection, and enabled capabilities. Four default packs ship across three domains: `medicare_fraud_cms_desynpuf.yaml` (default exemplar), `medicare_fraud.yaml` (minimal variant), `food_supply_chain.yaml` (exemplar-parity peer), and `department_air_force_housing.yaml` (statutory-oversight vertical). A base pack may additionally be layered with environment overlays via `CHILI_CONFIG_OVERLAY_PATH` (deep-merge + list-replace semantics, ADR 0001) — e.g. `medicare_fraud_dev.yaml`, a partial dev-environment overlay over `medicare_fraud.yaml`, not a standalone pack.
- **REQ-CONFIG-002** — The system shall expose the active domain configuration via a `GET /config/domain` API endpoint for frontend consumption.
- **REQ-CONFIG-003** — The system shall validate all entity and relationship instances against the loaded domain configuration at ingestion and graph-write time.
- **REQ-CONFIG-004** — The system shall render entity types, relationship types, and property labels dynamically in the frontend based on the fetched domain configuration.
- **REQ-CONFIG-005** *(amended v1.2: read-only → managed write)* — The system shall provide a Configuration Manager surface in the frontend enabling administrators to view the active configuration, discover and switch among shipped domain packs, and edit the active pack's YAML with inline dry-run validation before apply. The validated raw-YAML editor plus pack switcher is the v1 configuration-editing surface; the sectioned form-based wizard is post-v1 (see §6).
- **REQ-CONFIG-006** *(new v1.2)* — The system shall expose an admin-gated configuration write API: `GET /config/packs` (pack discovery + active-pack state), `POST /config/validate` (dry-run validation of a candidate pack or edited content), `POST /config/apply` (re-apply the on-disk active pack), and `POST /config/switch` (activate a different pack), with pack references confined to allow-listed configuration directories.
- **REQ-CONFIG-007** *(new v1.2)* — The system shall execute every configuration activation as a swap-once-success pipeline — full `DomainConfig` validation and the production guardrail run before any state mutates, and a failure at any step leaves the previously active domain fully in effect.
- **REQ-CONFIG-008** *(new v1.2)* — The system shall persist the active-pack selection durably via an atomically written pointer shared by the API and worker containers, surviving restarts and taking precedence over the `CHILI_CONFIG_PATH` environment variable until explicitly cleared.
- **REQ-CONFIG-009** *(new v1.2)* — The system shall hot-swap the active domain configuration on a running deployment without restart: the API atomically resets its config-derived dependency graph (a request observes a wholly-old or wholly-new graph, never a mix) and the worker rebuilds its pipeline on a `config.updated` event. Constraint: the event transport is swap-invariant — a pack must not change the events backend/URI across a hot-swap; changing the event transport requires a restart.
- **REQ-CONFIG-010** *(new v1.2)* — The system shall refuse, at boot and before any hot-swap under `CHILI_ENV=staging|production`, any domain pack that disables authentication or ships an incomplete OIDC configuration (production auth guardrail).
- **REQ-CONFIG-011** *(new v1.2 — post-v1 scope)* — The system shall harden the configuration write path with validated draft save/apply persistence, optimistic-concurrency control (ETag) on writes, and admin audit events for every configuration change. This requirement is post-v1 hardening (traces to config module stories config.06/07/09/14/15); the resulting v1 gap is recorded as an accepted deviation in §6.

### 3.10 Authentication & Authorization (v1 Scope)

- **REQ-AUTH-001** — The system shall support generic OIDC/OAuth2 authentication for production deployments with configurable issuer URL, client ID, JWKS URI, and redirect URI.
- **REQ-AUTH-002** — The system shall require a `chiliai_session` cookie or Bearer token for all protected routes when auth is enabled, with exemptions for `/auth/*`, `/docs`, `/openapi.json`, and `/health`.
- **REQ-AUTH-003** — The system shall enforce role-based access control (RBAC) with roles `viewer` (read-only), `analyst` (read + write), `service` (machine-to-machine), and `admin` (full control). The configuration write surface (REQ-CONFIG-006) is admin-only.
- **REQ-AUTH-004** — The system shall audit route policy completeness at startup and refuse to boot if any protected route lacks an explicit role annotation (default-deny enforcement).
- **REQ-AUTH-005** — The system shall support an auth-disabled mode for local development and testing, running as an anonymous `viewer`.
- **REQ-AUTH-006** — The system shall enforce knowledge-base-level isolation: all graph, vector, storage, and workflow queries are scoped by `knowledge_base_id`.

### 3.11 Frontend Analyst Workbench

- **REQ-UI-001** — The system shall provide a React 19 single-page application served as static assets over HTTPS.
- **REQ-UI-002** *(amended v1.2)* — The system shall implement the following routed pages: Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, Configuration — plus capability-gated pages contributed by the active domain configuration (e.g., Case Management, Policy Intelligence, Housing Executive).
- **REQ-UI-003** — The system shall display knowledge base lists, detail views, document inventories, and ingestion workflow timelines.
- **REQ-UI-004** — The system shall provide an interactive graph visualization using `react-force-graph-2d` with entity search, detail panels, and neighborhood expansion.
- **REQ-UI-005** — The system shall stream workspace snapshots (alert deltas, workflow status, KB metrics) to the frontend in real time. Server-Sent Events is the default transport; WebSocket is permitted per channel where bidirectional or low-latency push semantics are required (e.g. the alert stream).
- **REQ-UI-006** — The system shall dynamically render entity labels, relationship types, and feature gates based on the domain configuration fetched at startup.

### 3.12 Case Management

- **REQ-CASE-001** — The system shall allow analysts to promote an alert into an investigation case, capturing the originating alert, evidence pack, and entity timeline.
- **REQ-CASE-002** — The system shall persist cases (id, title, summary, status, owner, created_at, updated_at, linked alerts, linked entities) in a durable repository accessible across API and worker containers.
- **REQ-CASE-003** — The system shall provide case CRUD endpoints and a frontend Case Management surface for listing, detailing, updating status, and recording analyst feedback.
- **REQ-CASE-004** — The system shall scope all case queries by `knowledge_base_id` to enforce isolation.

### 3.13 Policy Intelligence

- **REQ-POLICY-001** — The system shall provide a Policy Intelligence queue surface in the frontend that lists policy-driven review items derived from domain-configured rules (e.g. Medicare LCD/NCD constraints, supply-chain compliance rules).
- **REQ-POLICY-002** — The system shall allow analysts to triage policy items (accept, reject, defer, escalate to case) and persist disposition state.
- **REQ-POLICY-003** — The system shall source policy items from configured rule packs tied to the active domain configuration; policy rule definitions are part of the domain config surface.
- **REQ-POLICY-004** — The system shall scope all policy intelligence queries by `knowledge_base_id`.

### 3.14 Object Storage & Audit

- **REQ-STORAGE-001** — The system shall persist raw uploaded files in a pluggable object store (local filesystem, S3, MinIO) for audit trail and reprocessing.
- **REQ-STORAGE-002** — The system shall namespace all stored objects by `knowledge_base_id` to enforce isolation.
- **REQ-STORAGE-003** — The system shall optionally use the object store as a single-writer durable projection for knowledge base metadata in development environments.

### 3.15 Scorecards Platform *(new v1.2 — BL-038)*

- **REQ-SCORE-001** — The system shall provide a generic, configuration-driven scorecard capability: the domain configuration defines scorecard templates (sections, metrics, formulas, thresholds, freshness windows, export formats) with no domain-specific types hardcoded in application code.
- **REQ-SCORE-002** — The system shall evaluate scorecard templates deterministically through a pure (no-I/O) evaluator supporting a bounded formula set (`ratio`, `sum`, `mean`, `weighted_mean`, `latest`), per-metric freshness windows, and pass/warn/fail threshold banding; missing inputs or degenerate denominators shall degrade the metric to `incomplete` rather than produce a wrong grade.
- **REQ-SCORE-003** — The system shall support exactly one grading direction per metric — higher-is-better (`pass_min`/`warn_min`/`fail_max`) or lower-is-better (`pass_max`/`warn_max`/`fail_min`) — rejecting mixed directions and overlapping bands at configuration load time.
- **REQ-SCORE-004** — The system shall persist scorecard runs durably (pluggable in-memory and Postgres repositories), scoped by `knowledge_base_id`, with the source-data snapshot content-hashed into the run identity for reproducibility and traceability.
- **REQ-SCORE-005** — The system shall expose a scorecard API to list configured templates, generate runs, list and detail runs, and export a run as JSON or Markdown.
- **REQ-SCORE-006** — The system shall source scorecard inputs from the knowledge base's ingested structured-record feeds, selected by scope and period and dated by real observation dates so freshness checks reflect genuine data recency.
- **REQ-SCORE-007** — The system shall include scorecard runs in the knowledge-base deletion cascade.
- **REQ-SCORE-008** — The system shall provide a frontend scorecard run viewer showing graded sections, per-metric health and completeness indicators, per-metric citations/traceability, and JSON/Markdown export. Run creation in v1 is API/tooling-driven; an analyst-facing generation UI is post-v1 (see §6).

### 3.16 Air Force Housing Domain Surface *(new v1.2 — BL-039)*

The Department of the Air Force housing pack is a supported product domain at exemplar tier — requirement-covered, maintained, and e2e-gated like the Medicare and food-supply-chain exemplars.

- **REQ-HOUSING-001** — The system shall ship a Department of the Air Force housing domain pack defining six file/export records feeds (UMD authorizations, BAH rates, housing inventory, market availability, area demographics, resident experience) and two statutory scorecard templates: unaccompanied housing (UH, 8 metrics) and military family housing (MFH, 12 metrics).
- **REQ-HOUSING-002** — Every housing scorecard metric shall trace to a congressional mandate, with statutory-vs-judgement threshold provenance labeled per metric and documented in the research dossier (`docs/research/housing-scorecard-mandates.md`), including the demo's honest simplifications.
- **REQ-HOUSING-003** — The system shall provide housing read endpoints (`/housing/overview`, `/housing/installations`) aggregating ingested feed rows into portfolio and per-installation rollups with statutorily informed `ok`/`watch`/`critical`/`unknown` status banding, where each status is accompanied by human-readable reasons derived from the same evaluation (band and explanation can never disagree).
- **REQ-HOUSING-004** — The system shall provide a Housing Executive dashboard rendering a self-contained CONUS map (no external tile servers) of all AF/SF installations with status/branch/size encodings, a summary band of executive KPIs (occupancy, condition index, satisfaction, overdue work-order rate, UH/MFH supply ratios) recomputed client-side over the filtered installation set with semantics identical to the overview API, status/branch/command filtering, a ranking table, and installation detail with status explanation and links into the scorecard run viewer.
- **REQ-HOUSING-005** — With no housing feed rows ingested, the dashboard shall fall back to a public installation reference layer with placeholder indicators and shall never fabricate metric values; installations without resolvable coordinates shall remain visible (listed, not silently dropped from the map).
- **REQ-HOUSING-006** — The system shall provide seed tooling that exercises the real running stack over HTTP (knowledge base creation, feed CSV upload via the records API, ingest workflow completion, optional scorecard run generation).
- **REQ-HOUSING-007** — v1 housing ingestion is file/export based; live connectors to external housing systems are out of scope (see §6).

## 4. Non-Functional Requirements

### 4.1 Performance & Scale

- **REQ-NFR-SCALE-DEMO** — The system shall support a demo profile of 1 concurrent user and 100,000 graph nodes without degradation.
- **REQ-NFR-SCALE-PROD** — The system shall support a production profile of 50 concurrent users and 100,000,000 graph nodes without degradation.
- **REQ-NFR-001** — The system shall use pyright --strict for backend code with full type annotations and no untyped `Any`.
- **REQ-NFR-002** — The system shall maintain ≥85% pytest coverage for affected backend packages with full green tests before acceptance.
- **REQ-NFR-003** — The system shall use TypeScript strict mode for frontend code (noUnusedLocals, noUnusedParameters, noFallthroughCasesInSwitch) and remain ESLint clean.

### 4.2 Security

- **REQ-NFR-SEC-001** — The system shall store all credentials in environment variables only, never in configuration files or committed code.
- **REQ-NFR-SEC-002** — The system shall validate all API request bodies using Pydantic v2 models with field-level constraints.
- **REQ-NFR-SEC-003** — The system shall compose all graph database queries using parameterized driver APIs to prevent injection.
- **REQ-NFR-SEC-004** — The system shall emit all logs through structured JSON with PII-stripping filters when applicable.
- **REQ-NFR-SEC-005** — The system shall run dependency vulnerability scanning (pip-audit, npm audit) in CI and fail on HIGH or CRITICAL findings.
- **REQ-NFR-SEC-006** — The system shall terminate TLS at the ingress/nginx edge in production, with backend services accepting only loopback HTTP inside the cluster.
- **REQ-NFR-SEC-007** *(new v1.2)* — The system shall gate all domain-configuration mutation (validate/apply/switch, and any future draft/write surface) behind the `admin` role and confine configuration file references to allow-listed directories (no arbitrary filesystem reads or writes via the config API).

### 4.3 Disaster Recovery & Durability

- **REQ-NFR-DR-001** — The system shall support point-in-time knowledge base snapshots and restoration procedures.
- **REQ-NFR-DR-002** — The system shall support graph database backup and restore procedures documented per adapter.
- **REQ-NFR-DR-003** — The system shall support event replay from persistent Redis Streams log for recovery of processing pipelines.

### 4.4 Deployment & Operations

- **REQ-NFR-OPS-001** — The system shall package as three Docker containers: chili-app (React SPA), chili-api (FastAPI gateway), chili-worker (pipeline runner).
- **REQ-NFR-OPS-002** — The system shall support Docker Compose for local development with hot reload and Kubernetes for production deployment.
- **REQ-NFR-OPS-003** — The system shall require explicit `CHILI_ENV` setting (local, dev, staging, production) and refuse to boot on unset or unknown values.
- **REQ-NFR-OPS-004** — The system shall provide health-check endpoints (`/health`) for API and worker containers for orchestrator liveness/readiness probes.

## 5. Integration & Adapter Requirements

- **REQ-INT-001** — The system shall access every external system (graph DB, vector store, LLM, embeddings, object storage, event bus, relational DB) through an abstract Protocol with concrete adapter implementations.
- **REQ-INT-002** — The system shall select adapters at runtime based on domain configuration fields (e.g., `graph.backend: neo4j`, `vector.backend: qdrant`).
- **REQ-INT-003** — The system shall provide in-memory adapters for all protocols to enable isolated, fast unit tests without external dependencies.
- **REQ-INT-004** — The system shall support the following production-grade adapters at v1: Neo4j (graph), Qdrant (vector), OpenAI & Anthropic & Ollama (LLM), OpenAI & sentence-transformers (embeddings), S3/MinIO (object storage), Redis Streams (event bus), Postgres + TimescaleDB (relational/time-series).
- **REQ-INT-005** — The system shall document how to add new adapters (e.g., Memgraph, pgvector, Weaviate) via the adapter pattern without modifying business logic.
- **REQ-INT-006** — The system shall ingest structured records from pull-based origin sources — object store (local FS/S3/MinIO), HTTP API, and event stream — by reference, through the records source-adapter protocol, without HTTP upload size constraints (stories records.14–records.17).

## 6. Out of Scope (v1)

- **Full tenant isolation** — Multi-tenancy in v1 is limited to knowledge-base-level isolation. Separate tenant namespaces across all data and configuration are not in scope for v1.
- **Tenant management UI** — Creating, updating, and deleting tenants via a UI is out of scope for v1.
- **Specific IdP vendor requirements** — While generic OIDC/OAuth2 is in scope, prescriptive integration recipes for specific vendors (Auth0, Okta, Cognito, Keycloak, Google Workspace) are deferred to production hardening.
- **Third-party plugin SPI (service provider interface)** — A public API for third-party developers to add custom analytics, extractors, or UI panels is post-v1. An SPI design will be revisited after v1 release.
- **Resource-level authorization** — v1 implements route-level RBAC (viewer, analyst, admin). Granular per-entity or per-KB authorization policies are deferred.
- **Event-transport-crossing hot-swap** *(replaces "Configuration hot-reload", which shipped 2026-07-04 as BL-037)* — Hot-swapping the active domain pack without restart is in scope (REQ-CONFIG-009); however, a swap that changes the event transport backend/URI requires an application restart. Full transport-crossing hot-swap is post-v1.
- **Sectioned configuration wizard** — Structured form-based pack editing is post-v1; v1 ships the validated raw-YAML editor plus pack switcher (REQ-CONFIG-005).
- **Raw domain-pack file read/write endpoint** — The config API deliberately exposes no arbitrary pack file read/write; edits are validated inline and apply re-reads the on-disk pack. A managed write endpoint is charted with the post-v1 config-write hardening (REQ-CONFIG-011).
- **Config change audit trail & optimistic concurrency (accepted deviation)** — v1 configuration changes carry no audit trail, version history, draft persistence, or optimistic-concurrency (ETag) guarantees. This is an accepted risk pending the post-v1 hardening in REQ-CONFIG-011; mitigations in v1 are admin-only gating (REQ-NFR-SEC-007) and the swap-once-success validation pipeline (REQ-CONFIG-007).
- **Analyst-facing scorecard-generation UI** — Scorecard run creation in v1 is API/tooling-driven (the dashboard's generation surface was deliberately retired 2026-07-07); a UI trigger is post-v1 if a domain demands it.
- **Live housing data connectors** — Direct integration with DAF/DoD housing systems of record is out of scope for v1; the housing domain ingests file/export extracts only (REQ-HOUSING-007).
- **Production-grade observability stack** — While structured logging and basic metrics instrumentation are in scope, a prescriptive observability stack (Prometheus, Grafana, Jaeger, retention policies, alert rules) is deferred.
- **CI/CD pipelines & GitOps** — Automated deploy pipelines, environment promotion workflows, and Infrastructure-as-Code templates (Helm, Terraform, Pulumi) are tracked in backlog but not required for v1.
- **Frontend real-user monitoring (RUM)** — Client-side performance telemetry and error tracking are post-v1.
- **Advanced evidence pack workflows** *(amended v1.2: persisted evidence-pack storage shipped as BL-005 and is no longer deferred)* — Multi-analyst collaboration on evidence and evidence versioning are deferred beyond persisted, alert-attached evidence packs in v1.

## 7. Assumptions

All blocking open questions raised during the v1.2 refresh were resolved by product-owner ruling on 2026-07-12. The following are documented, confirmed assumptions:

- **[ASSUMPTION]** Query latency targets (p50, p95, p99) for graph queries, vector similarity search, and RAG answer generation will be specified after initial performance profiling in a production-like environment.
- **[ASSUMPTION]** Ingest throughput targets (documents/hour, records/hour) will be specified after load testing with representative Medicare and food supply chain datasets.
- **[ASSUMPTION]** Observability stack selection (specific logging aggregator, metrics backend, tracing backend, retention policies, alerting rules) will be specified in a later requirements refresh once deployment profiles are finalized.
- **[ASSUMPTION]** The third-party plugin SPI design (extension points, API surface, security model, packaging) will be revisited after v1 release based on early adopter feedback.
- **[ASSUMPTION]** *(new v1.2, confirmed)* The scorecards capability is generic platform scope; the housing pack is its first consumer, and future domains are expected to define scorecard templates without application code changes.
- **[ASSUMPTION]** *(new v1.2, confirmed)* All shipped housing feed data are synthetic demo fixtures; a production deployment would ingest real installation extracts through the same feed schemas and would surface the GAO-documented condition-score reliability caveats alongside affected metrics.
- **[ASSUMPTION]** *(new v1.2, confirmed)* The housing surface targets an executive/portfolio-oversight audience rather than installation housing-office operational staff.
- **[ASSUMPTION]** *(new v1.2, confirmed)* Event-transport swap-invariance (REQ-CONFIG-009 constraint) is an accepted permanent design constraint of hot-swap, not a temporary limitation.

## 8. Source Material

This artifact was synthesized from the following planning docs, READMEs, and instruction files, last read 2026-07-12:

- `docs/architecture.md` (design source of truth — §6.8 housing scorecards & dashboard, §9.2–9.3 active-pack pointer & hot-swap)
- `CLAUDE.md` and `.github/copilot-instructions.md` (agent operating rules)
- `README.md`, `backend/README.md`, `backend/config/README.md`, `chili_app/README.md` (module overviews)
- `docs/project/planning/backlog.md` v2 (2026-07-12 PM grooming — BL-016/BL-037/BL-038/BL-039, [NO-REQ] flags)
- `docs/backlog/config.md` (config module stories, esp. config.05–.15)
- `docs/superpowers/plans/2026-07-06-air-force-housing-scorecards.md` (goal & architecture sections)
- `docs/research/housing-scorecard-mandates.md` (statutory basis, metric catalog, honest simplifications)
- `docs/onboarding.md`, `docs/security_checklist.md`
- Prior version: requirements v1.1 (2026-05-26)
- Open-question rulings: product-owner delegation via coordinator, 2026-07-12 (OQ-1 wizard post-v1; OQ-2 write-hardening post-v1 with accepted deviation; OQ-3 API-only run generation; OQ-4 housing as supported exemplar-tier domain)
