# chiliAI Product Requirements

> Canonical product scope owned by the Requirements Gatherer agent.
> Version: 1.1 · Last updated: 2026-05-26 (drift-resolution amendments applied during PM sprint plan)

## 1. Product Vision

chiliAI is a **domain-reconfigurable Graph RAG analytics platform** that combines knowledge-graph construction, vector-based retrieval-augmented generation, graph neural networks, time-series analysis, anomaly detection, and explainable AI into a single, loosely coupled system. A single YAML/JSON configuration surface retargets the entire application to different investigation domains (Medicare fraud, food supply chain, financial crime, etc.) without code changes, enabling analysts to build knowledge bases, monitor live data streams, surface alerts with evidence, explore entity graphs, and converse with the knowledge through an LLM-powered interface — all within a rich browser-based workbench.

## 2. Target Users & Domains

- **Primary users:** Fraud investigators, compliance analysts, supply-chain auditors, and intelligence analysts working on entity-and-relationship-centric investigations.
- **Supported domains (exemplars):** Medicare fraud detection (initial), food supply chain monitoring, financial crime, and any domain requiring entity graph construction, RAG retrieval, anomaly detection, and evidence-driven investigation. The platform is designed so that adding a new domain requires only a configuration change, not application code changes.

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

### 3.9 Domain Configuration

- **REQ-CONFIG-001** — The system shall load a single YAML/JSON domain configuration at startup defining entity types, relationship types, property schemas, display labels, feed schemas, thresholds, policy rule packs, and enabled capabilities. Two default configurations ship with v1: `medicare_fraud.yaml` (primary exemplar) and `food_supply_chain.yaml` (secondary reference).
- **REQ-CONFIG-002** — The system shall expose the active domain configuration via a `GET /config/domain` API endpoint for frontend consumption.
- **REQ-CONFIG-003** — The system shall validate all entity and relationship instances against the loaded domain configuration at ingestion and graph-write time.
- **REQ-CONFIG-004** — The system shall render entity types, relationship types, and property labels dynamically in the frontend based on the fetched domain configuration.
- **REQ-CONFIG-005** — The system shall provide a read-only domain configuration editor in the frontend showing the active configuration schema.

### 3.10 Authentication & Authorization (v1 Scope)

- **REQ-AUTH-001** — The system shall support generic OIDC/OAuth2 authentication for production deployments with configurable issuer URL, client ID, JWKS URI, and redirect URI.
- **REQ-AUTH-002** — The system shall require a `chiliai_session` cookie or Bearer token for all protected routes when auth is enabled, with exemptions for `/auth/*`, `/docs`, `/openapi.json`, and `/health`.
- **REQ-AUTH-003** — The system shall enforce role-based access control (RBAC) with roles `viewer` (read-only), `analyst` (read + write), `service` (machine-to-machine), and `admin` (full control).
- **REQ-AUTH-004** — The system shall audit route policy completeness at startup and refuse to boot if any protected route lacks an explicit role annotation (default-deny enforcement).
- **REQ-AUTH-005** — The system shall support an auth-disabled mode for local development and testing, running as an anonymous `viewer`.
- **REQ-AUTH-006** — The system shall enforce knowledge-base-level isolation: all graph, vector, storage, and workflow queries are scoped by `knowledge_base_id`.

### 3.11 Frontend Analyst Workbench

- **REQ-UI-001** — The system shall provide a React 19 single-page application served as static assets over HTTPS.
- **REQ-UI-002** — The system shall implement the following routed pages: Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, Configuration.
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

## 6. Out of Scope (v1)

- **Full tenant isolation** — Multi-tenancy in v1 is limited to knowledge-base-level isolation. Separate tenant namespaces across all data and configuration are not in scope for v1.
- **Tenant management UI** — Creating, updating, and deleting tenants via a UI is out of scope for v1.
- **Specific IdP vendor requirements** — While generic OIDC/OAuth2 is in scope, prescriptive integration recipes for specific vendors (Auth0, Okta, Cognito, Keycloak, Google Workspace) are deferred to production hardening.
- **Third-party plugin SPI (service provider interface)** — A public API for third-party developers to add custom analytics, extractors, or UI panels is post-v1. An SPI design will be revisited after v1 release.
- **Resource-level authorization** — v1 implements route-level RBAC (viewer, analyst, admin). Granular per-entity or per-KB authorization policies are deferred.
- **Configuration hot-reload** — Changing the domain configuration requires an application restart in v1. Hot-reload of configuration without downtime is post-v1.
- **Production-grade observability stack** — While structured logging and basic metrics instrumentation are in scope, a prescriptive observability stack (Prometheus, Grafana, Jaeger, retention policies, alert rules) is deferred.
- **CI/CD pipelines & GitOps** — Automated deploy pipelines, environment promotion workflows, and Infrastructure-as-Code templates (Helm, Terraform, Pulumi) are tracked in backlog but not required for v1.
- **Frontend real-user monitoring (RUM)** — Client-side performance telemetry and error tracking are post-v1.
- **Advanced evidence pack workflows** — Persisted evidence pack storage, multi-analyst collaboration on evidence, and evidence versioning are deferred beyond basic alert-attached evidence in v1.

## 7. Assumptions

All blocking open questions have been resolved. The following items are documented assumptions to be specified in a future requirements refresh:

- **[ASSUMPTION]** Query latency targets (p50, p95, p99) for graph queries, vector similarity search, and RAG answer generation will be specified after initial performance profiling in a production-like environment.
- **[ASSUMPTION]** Ingest throughput targets (documents/hour, records/hour) will be specified after load testing with representative Medicare and food supply chain datasets.
- **[ASSUMPTION]** Observability stack selection (specific logging aggregator, metrics backend, tracing backend, retention policies, alerting rules) will be specified in a later requirements refresh once deployment profiles are finalized.
- **[ASSUMPTION]** The third-party plugin SPI design (extension points, API surface, security model, packaging) will be revisited after v1 release based on early adopter feedback.

## 8. Source Material

This artifact was synthesized from the following planning docs, READMEs, and instruction files, last read 2026-05-26:

- `docs/architecture.md` (design source of truth)
- `CLAUDE.md` (agent operating rules)
- `.github/copilot-instructions.md` (condensed operating rules)
- `README.md` (root repository overview)
- `backend/README.md` (backend module overview)
- `chili_app/README.md` (frontend overview)
- `docs/backlog/README.md` and per-module backlogs (`docs/backlog/agent.md`, `docs/backlog/graph.md`, `docs/backlog/ingestion.md`, etc.)
- `docs/backlog/_multitenancy.md`, `docs/backlog/_security.md`, `docs/backlog/_observability.md`, `docs/backlog/_plugins.md` (cross-cutting concerns)
- `docs/security_checklist.md` (OWASP mapping and controls)
- `docs/superpowers/plans/*.md` (design specs for major features)
