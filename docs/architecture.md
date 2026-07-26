# chiliAI — High-Level Architecture & Design

> **Status**: Target architecture plus implementation status notes. The repository is now an active prototype with substantial backend and frontend implementation. This document describes the intended system design and calls out current-state gaps where relevant.
>
> **Detailed diagram**: See [`system_architecture_diagram.md`](system_architecture_diagram.md) for a Mermaid view of the runtime containers, services, adapters, request flows, and deployment mapping.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Guiding Principles](#2-guiding-principles)
3. [System Context (C4 Level 1)](#3-system-context-c4-level-1)
4. [Container Diagram (C4 Level 2)](#4-container-diagram-c4-level-2)
5. [Backend Module Decomposition](#5-backend-module-decomposition)
6. [Data Flow & Pipeline Architecture](#6-data-flow--pipeline-architecture)
7. [Knowledge Base Management](#7-knowledge-base-management)
8. [Frontend Architecture](#8-frontend-architecture)
9. [Domain Configuration Model](#9-domain-configuration-model)
10. [Deployment Architecture](#10-deployment-architecture)
11. [Observability](#11-observability)
12. [Security](#12-security)
13. [Technology Stack Summary](#13-technology-stack-summary)
14. [Open Questions & Future Work](#14-open-questions--future-work)

---

## 1. Executive Summary

chiliAI is a **domain-reconfigurable Graph RAG analytics platform**. It combines knowledge-graph construction, vector-based retrieval-augmented generation, graph neural networks, time-series analysis, anomaly detection, and explainable AI into a single, loosely coupled system that an analyst can operate through a rich browser-based workbench.

The platform is designed to be **retargeted to different investigation domains** — Medicare fraud, food supply chain monitoring, financial crime, or any entity-and-relationship-centric analysis problem — by changing a single configuration surface rather than rewriting application code.

### Starting exemplar: Medicare fraud detection

The initial deployment scenario follows this workflow:

1. **Build the policy knowledge base** — Ingest Medicare policy documents, extract entities and relationships, construct a knowledge graph, embed and index text and graph metrics for RAG retrieval.
2. **Active monitoring** — Stream claims records, beneficiary data, provider information, and medical records. Extract, normalize, and integrate this data into a claims knowledge graph.
3. **Analysis loop** — Run time-series anomaly detection, GNN-based link prediction and clustering, and risk scoring. Results feed back into the graph and forward to the analyst workbench.
4. **Alert & investigate** — Surface warnings with evidence packs (reasoning, subgraph patterns, scores). Analysts explore the graph, drill into entities, and converse with the knowledge base through an LLM-powered chat interface.

### Value proposition

| Concern | How chiliAI addresses it |
|---------|--------------------------|
| Vendor lock-in | Abstract interfaces + adapter pattern for graph DB, vector store, LLM, and object storage |
| Domain specificity | Single YAML/JSON configuration surface for entity types, relationships, display labels, and enabled capabilities |
| Analyst productivity | Full investigation workbench — interactive graph, evidence panels, timeline, risk scores, and conversational RAG |
| Extensibility | Loosely coupled capability modules; new analytics can be added without modifying existing pipelines |
| Deployment flexibility | Containerized, deployable to cloud Kubernetes or on-premises Docker/Compose |

---

## 2. Guiding Principles

### 2.1 Vendor-agnostic integrations

Every external system (graph database, vector store, LLM provider, object storage) is accessed through an **abstract protocol** with concrete **adapter** implementations. The application never imports vendor SDKs directly in business logic — only inside adapter modules.

### 2.2 Loose coupling and narrow module boundaries

Backend modules are organized by **capability domain** (ingestion, graph access, analytics, RAG, etc.). Each module owns its internal implementation and exposes a narrow public contract.

Cross-module interaction is restricted to exactly three permitted paths:

| Path | When to use | Example |
|------|-------------|---------|
| **A — FastAPI gateway orchestration** | When an API boundary is appropriate (frontend-initiated actions) | UI request → API router → calls ingestion service + graph service → response |
| **B — Agent / workflow coordinator** | When interaction is process-driven or multi-step | Agent step triggers ingestion → event → analytics → event → alert creation |
| **C — Lightweight shared library** | For stable contracts, shared types, and small utilities | `shared.types.Entity` imported by both `ingestion` and `graph` to define the contract |

**Forbidden**: ad hoc cross-module imports, hidden shared state, direct implementation coupling (e.g., `analytics` importing from `ingestion`; `graph` importing from `api`).

### 2.3 Domain reconfigurability

A single configuration surface (YAML/JSON file or UI-driven wizard) defines entity types, relationship types, display labels, data-source formats, enabled capabilities, and alert thresholds. The frontend reads this configuration at startup to dynamically render labels and feature gates.

### 2.4 Interface-first design

Depend on **protocols** (Python `Protocol`), **abstract base classes**, or **narrow typed contracts** rather than concrete implementations. This enables testability, adapter swapping, and incremental buildout.

### 2.5 Strict typing

- **Backend**: Python 3.12. All code is written to be `pyright --strict`-compatible — full annotations, no untyped `Any`, explicit domain types. The enforced gate is bare `pyright`, whose strict scope is `tool.pyright.include` in `backend/pyproject.toml`; modules are added to `include` as they are hardened, with full-tree inclusion the end state.
- **Frontend**: TypeScript in strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`).

### 2.6 Test-driven quality

Backend test suites must maintain **≥ 85% coverage** for affected packages (the project standard, checked in review; the CI gate enforces the aggregate `--cov-fail-under=85`). Missing tests are treated as incomplete work. Tests are isolated and deterministic — external systems are mocked or faked at the adapter boundary.

---

## 3. System Context (C4 Level 1)

This section describes chiliAI's external actors and the systems it interacts with.

```
                          ┌─────────────────┐
                          │   Analyst User   │
                          │   (Browser)      │
                          └────────┬─────────┘
                                   │ HTTPS / WSS
                                   ▼
                          ┌─────────────────┐
                          │                 │
                          │    chiliAI      │
                          │    Platform     │
                          │                 │
                          └──┬──┬──┬──┬──┬──┘
                             │  │  │  │  │
              ┌──────────────┘  │  │  │  └──────────────┐
              ▼                 ▼  │  ▼                  ▼
     ┌────────────┐  ┌──────────┐ │ ┌──────────┐  ┌──────────┐
     │ Data       │  │ Graph    │ │ │ Vector   │  │ Object   │
     │ Sources    │  │ Database │ │ │ Store    │  │ Store    │
     │ (claims,   │  │ (Neo4j,  │ │ │ (pgvec,  │  │ (S3,     │
     │ docs, etc.)│  │ Memgraph,│ │ │ Qdrant,  │  │ MinIO,   │
     └────────────┘  │ Neptune) │ │ │ Weaviate)│  │ local)   │
                     └──────────┘ │ └──────────┘  └──────────┘
                                  ▼
                        ┌──────────────┐
                        │ LLM Provider │
                        │ (OpenAI,     │
                        │ Anthropic,   │
                        │ Ollama/vLLM) │
                        └──────────────┘
```

### External actors

| Actor / System | Role |
|----------------|------|
| **Analyst user** | Interacts with the platform through the browser-based workbench. Uploads documents, reviews alerts, explores the graph, queries via RAG chat. |
| **Data sources** | Claims records, beneficiary information, provider data, medical records, policy documents. Formats include PDF, DOCX, HTML, JSON, TXT, CSV. Delivered via file upload, API push, or polled feed. |
| **Graph database** | Stores knowledge graphs (policy graph, claims graph). Current selectable backends are in-memory and Neo4j behind an abstract adapter. Memgraph and AWS Neptune remain roadmap adapters until their adapter/factory wiring exists. |
| **Vector store** | Stores embeddings for RAG retrieval and similarity search. Current selectable backends are in-memory and Qdrant behind an abstract adapter. pgvector and Weaviate remain roadmap adapters until their adapter/factory wiring exists. |
| **LLM provider** | Powers RAG conversational interface and entity extraction during ingestion. Vendor-agnostic — OpenAI, Anthropic, or self-hosted (Ollama, vLLM) behind an abstract adapter. |
| **Object store** | Persists raw ingested files for audit and reprocessing. The dev stack can also use the object store as a single-writer durable KB metadata projection. S3, MinIO, or local filesystem sit behind an abstract adapter. |
| **Auth provider** | External identity provider (OIDC/OAuth2). Auth/RBAC middleware, `/auth/*` routes, cookie/Bearer token handling, and frontend login/session flow are implemented (completed 2026-05-08). Production IdP profiles, tenant isolation, and resource-level authorization remain future hardening. |

---

## 4. Container Diagram (C4 Level 2)

The monorepo produces the following deployable containers:

```
┌──────────────────────────────────────────────────────────────────────┐
│                         chiliAI Platform                             │
│                                                                      │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │              │    │                  │    │                   │  │
│  │  chili_app   │───▶│  Backend API     │───▶│  Worker /         │  │
│  │  (React SPA) │    │  (FastAPI)       │    │  Pipeline Runner  │  │
│  │              │    │                  │    │                   │  │
│  └──────────────┘    └───────┬──────────┘    └────────┬──────────┘  │
│                              │                        │             │
│                              │    ┌───────────┐       │             │
│                              └───▶│   Redis   │◀──────┘             │
│                                   │  Streams  │                     │
│                                   └───────────┘                     │
└──────────────────────────────────────────────────────────────────────┘
         │                    │                      │
         ▼                    ▼                      ▼
   ┌───────────┐     ┌──────────────┐       ┌──────────────┐
   │ Graph DB  │     │ Vector Store │       │ Object Store │
   └───────────┘     └──────────────┘       └──────────────┘
```

### Container responsibilities

| Container | Technology | Responsibility |
|-----------|-----------|----------------|
| **chili_app** | React 19, TypeScript, Vite 8 | Single-page application served as static assets (nginx or CDN). Full analyst workbench: graph explorer, alert feed, knowledge base manager, RAG chat, domain config editor. |
| **Backend API** | Python 3.12, FastAPI | HTTP + WebSocket entry point for the frontend. Thin orchestration layer — routes requests to internal service modules, publishes events, pushes real-time updates. **No business logic in routers.** |
| **Worker / Pipeline Runner** | Python 3.12, shares backend codebase | Long-running process(es) consuming events from Redis Streams. Executes ingestion, entity extraction, graph building, embedding, analytics pipelines, and alert generation. Scales via Redis consumer groups. |
| **Redis** | Redis 7+ with Streams | Event-driven pipeline orchestration. Decouples API from worker. Also stores shared operational workflow-run state when `CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`, allowing API and worker containers to observe the same lifecycle updates. |
| **Graph Database** | in-memory / Neo4j | Persists knowledge graphs. Accessed exclusively through the `graph` module's abstract repository protocol. |
| **Vector Store** | in-memory / Qdrant | Persists embeddings. Accessed exclusively through the `vectorstore` module's abstract protocol. |
| **Object Store** | S3 / MinIO / local FS | Persists raw uploaded files for audit trail and reprocessing. Accessed through an abstract storage protocol. |
| **Postgres / TimescaleDB** | PostgreSQL + TimescaleDB extension | Persists structured records, time-series observations, entity metric history (hypertable), current entity metrics, risk score history, alert history, cases, policy items, conversations, `entity_derived_signals`, scorecard runs, and the per-document ingestion status projection (`source_document_status`). Accessed exclusively through the `database` module's `ConnectionProvider` protocol and Alembic-managed schema. |

### Communication patterns

| From → To | Protocol | Purpose |
|-----------|----------|---------|
| chili_app → Backend API | HTTPS (REST) | CRUD operations, queries, file uploads |
| chili_app ← Backend API | SSE / WSS | Real-time workspace snapshots over SSE; WebSocket support remains available for push-style interactions |
| Backend API → Redis | Redis Streams XADD | Publish pipeline events (`documents.uploaded`, `claims.ingested`, etc.) |
| Worker ← Redis | Redis Streams XREADGROUP | Consume pipeline events, execute processing steps |
| Worker → Redis | Redis Streams XADD | Publish downstream events (`entities.extracted`, `risk.scored`, `alerts.created`, etc.) |
| Backend API / Worker → Redis | Redis key/value + sorted sets | Shared workflow-run operational state behind `agent.adapters.WorkflowRunStoreProtocol` |
| Backend API / Worker → Graph DB | Adapter-specific driver | Graph CRUD, queries, metrics |
| Backend API / Worker → Vector Store | Adapter-specific client | Embedding storage, similarity search |
| Worker → Object Store | Adapter-specific SDK | Raw file persistence |
| Backend API / Worker → LLM | Adapter-specific HTTP | Entity extraction, RAG answer generation |

---

## 5. Backend Module Decomposition

### 5.1 Package tree

> Capability modules (graph, vectorstore, embeddings, llm, rag, ingestion, records, monitoring, and each `analytics/*` submodule) follow a common shape: `service.py`, `service_models.py`, `protocols.py`, `models.py`, `exceptions.py`, and an `adapters/` subpackage. Only deviations from that template are called out below. `alembic.ini` lives at the `backend/` root; the Alembic environment and versioned migrations live under `backend/database/migrations/`.

```
backend/
├── main.py                     # Local Uvicorn launcher
├── pyproject.toml              # Project metadata, dependencies
├── alembic.ini                 # Alembic config (script_location → database/migrations)
├── api/                        # FastAPI gateway layer
│   ├── __init__.py
│   ├── app.py                  # FastAPI application factory (create_app)
│   ├── dependencies.py         # Dependency injection wiring
│   ├── state.py                # Application state container assembled at startup
│   ├── contracts.py            # API-facing request/response models
│   ├── _housing_read_model.py  # Housing overview/installation read models over feed records
│   ├── _kb_busy.py             # Workflow/pending-cleanup mutation guard
│   ├── _kb_projection.py       # KB read projection updated from events
│   ├── _rag_bridges.py         # RAG <-> KB document/entity bridges
│   ├── _workflow_projection.py # Worker-updated workflow lifecycle projection
│   ├── middleware/
│   │   ├── auth.py             # JWT/cookie/Bearer auth middleware
│   │   ├── rbac.py             # require_role dependency factory
│   │   ├── session_store.py    # chiliai_session cookie session store
│   │   ├── policy_registry.py  # Route policy registry (default-deny audit)
│   │   ├── metrics.py          # HTTP metrics middleware
│   │   └── exceptions.py
│   └── routers/
│       ├── knowledgebases.py   # KB CRUD, document management
│       ├── records.py          # Structured-record submission endpoints
│       ├── housing.py          # Air Force housing dashboard read endpoints (/housing/*)
│       ├── scorecards.py       # Scorecard templates/runs/exports (/scorecards/*)
│       ├── alerts.py           # Alert feed, acknowledgment
│       ├── investigation.py    # Investigation queries
│       ├── graph.py            # Graph queries, entity detail
│       ├── cases.py            # Investigation cases
│       ├── evidence.py         # Evidence-pack endpoints (/evidence-packs)
│       ├── rag.py              # RAG chat endpoints (mounted at /chat)
│       ├── analytics.py        # Analytics endpoints
│       ├── workflows.py        # Workflow run history
│       ├── events.py           # SSE workspace snapshot stream
│       ├── ws.py               # WebSocket hub for real-time push
│       ├── auth.py             # /auth/login, /auth/logout, /auth/me
│       ├── _oidc_client.py     # OIDC client helpers used by auth router
│       ├── policy.py           # Policy Intelligence items/triage (BL-011)
│       └── config.py           # Domain configuration endpoints
├── ingestion/                  # Document parsing & entity extraction
│   ├── __init__.py
│   ├── service.py              # IngestionService orchestration
│   ├── service_models.py
│   ├── protocols.py
│   ├── models.py               # DocumentFormat enum, ParsedDocument, SourceDocument
│   ├── chunker.py              # Text chunking strategies
│   ├── extractor.py            # Entity & relationship extraction (uses LLM adapter)
│   ├── validator.py            # Source validation
│   ├── orchestrators/          # Batch, format resolution, and source-document helpers
│   ├── parsers/                # Format-specific parsers
│   │   ├── registry.py         # ParserRegistry, create_default_registry
│   │   ├── protocols.py
│   │   ├── pdf.py, docx.py, html.py, txt.py, json.py, csv.py, xlsx.py
│   │   └── remote.py           # Fetch-and-parse for remote URLs
│   └── adapters/                # Durable per-document status projection (BL-041)
│       ├── protocols.py        # SourceDocumentStatusStore (apply/get_many/list/delete_by_kb/delete_by_document)
│       ├── in_memory.py        # InMemorySourceDocumentStatusStore
│       └── postgres.py         # PostgresSourceDocumentStatusStore (source_document_status table, migration 0009_document_status)
├── graph/                      # Graph database access
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   ├── auth.py                 # Graph-scoped authorization helpers
│   └── adapters/
│       ├── protocols.py
│       ├── in_memory.py
│       └── neo4j_adapter.py
├── vectorstore/                # Vector store access
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   └── adapters/
│       ├── protocols.py
│       ├── in_memory.py
│       └── qdrant_adapter.py
├── embeddings/                 # Embedding generation
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   ├── metrics.py              # Prometheus usage counters + token estimation (BL-019)
│   └── adapters/
│       ├── in_memory.py
│       ├── cache_in_memory.py  # Per-process LRU embedding cache (BL-019)
│       ├── openai_adapter.py
│       └── sentence_transformers_adapter.py
├── rag/                        # Retrieval-augmented generation pipeline
│   ├── __init__.py
│   ├── service.py              # Query → embed → search → expand → assemble → LLM → answer
│   ├── service_models.py, protocols.py, models.py, exceptions.py
│   ├── auth.py
│   └── adapters/
│       ├── protocols.py
│       └── in_memory.py
├── llm/                        # LLM client abstraction
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   ├── factory.py              # create_llm_client() — builds adapter + FallbackLlmClient chain
│   └── adapters/
│       ├── in_memory.py
│       ├── openai_adapter.py
│       ├── anthropic_adapter.py
│       ├── ollama_adapter.py   # OllamaLlmClient (provider="ollama", LlmConfig.base_url)
│       └── fallback.py         # FallbackLlmClient — wraps primary + ordered fallback list
├── analytics/                  # ML / AI capability modules
│   ├── __init__.py
│   ├── timeseries/             # Self-history anomaly detection (standard module shape)
│   │   └── adapters/
│   │       ├── in_memory.py         # InMemoryTimeSeriesHistorySource, InMemoryTimeseriesAnomalyStore
│   │       ├── postgres.py          # PostgresTimeSeriesHistorySource (entity_metric_history), PostgresTimeseriesAnomalyStore (timeseries_anomalies)
│   │       └── record_aggregates.py # RecordAggregateTimeSeriesSource — per-entity series over raw_records aggregates (reuses peerstats RecordColumnSourceProtocol)
│   ├── gnn/                    # Graph neural network analysis (standard module shape)
│   │   └── adapters/
│   │       ├── in_memory.py
│   │       ├── graph_repository_source.py  # GraphSnapshotSourceProtocol over any GraphRepository, bounded by gnn.snapshot_max_nodes
│   │       └── cluster_store.py            # ClusterSummaryStoreProtocol: in-memory + object-store adapters
│   ├── risk/                   # Risk scoring engine (standard module shape)
│   │   └── adapters/
│   │       ├── in_memory.py
│   │       ├── linear_strategy.py
│   │       └── postgres.py     # Writer-only risk history persistence
│   ├── explainability/         # Evidence pack generation (standard module shape)
│   │   └── adapters/
│   │       ├── in_memory.py
│   │       ├── shap_adapter.py
│   │       ├── evidence_in_memory.py
│   │       ├── evidence_object_store.py
│   │       └── protocols.py
│   ├── metrics/                # Entity-metric persistence (no service, no events)
│   │   ├── __init__.py
│   │   ├── models.py           # EntityMetric, EntityMetricSnapshot
│   │   ├── exceptions.py
│   │   ├── throttle.py         # MetricsRecomputeThrottle — per-KB rate limiter
│   │   └── adapters/
│   │       ├── protocols.py    # EntityMetricRepository protocol
│   │       ├── in_memory.py
│   │       └── postgres.py     # PostgresEntityMetricRepository
│   └── peerstats/              # Cross-sectional peer-group z-score analytics (gated: capabilities.peer_stats)
│       ├── __init__.py
│       ├── service.py          # PeerStatsService.compute() — aggregate → z-score → signal
│       ├── service_models.py   # PeerStatsComputeRequest / PeerStatsComputeResponse
│       ├── models.py           # PeerAggregate / DerivedRiskSignal
│       ├── protocols.py        # RecordColumnSourceProtocol, DerivedRiskSignalWriterProtocol
│       ├── aggregation.py      # Pure interval-bucketing + population z-score helpers
│       ├── exceptions.py
│       └── adapters/
│           ├── in_memory.py    # InMemoryRecordColumnSource / InMemoryDerivedRiskSignalWriter
│           └── postgres.py     # PostgresRecordColumnSource (raw_records JSONB) / PostgresDerivedRiskSignalWriter (entity_derived_signals)
├── agent/                      # Workflow / pipeline coordinator
│   ├── __init__.py
│   ├── coordinator.py          # Worker entrypoint + event consumer + Plan C handlers
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   ├── health.py               # Optional health-check HTTP endpoint
│   ├── workflow_tracking.py    # WorkflowEventTracker
│   └── adapters/               # WorkflowRunStore implementations
│       ├── protocols.py
│       ├── in_memory.py
│       ├── redis_store.py
│       └── runtime.py          # create_workflow_run_store_from_env
├── knowledgebases/             # KB and document metadata persistence
│   ├── __init__.py             # Re-exports the public surface
│   ├── protocols.py            # KnowledgeBaseRepository Protocol
│   ├── models.py               # DocumentRecord
│   ├── snapshots.py            # KnowledgeBaseStoreSnapshot (object-store serialization)
│   ├── _helpers.py             # Shared internal helpers
│   └── adapters/
│       ├── in_memory.py        # InMemoryKnowledgeBaseRepository
│       └── object_store.py     # ObjectStoreKnowledgeBaseRepository
├── monitoring/                 # Active monitoring service
│   ├── __init__.py
│   ├── service.py, service_models.py, protocols.py, models.py, exceptions.py
│   ├── metrics.py              # Threshold evaluation helpers
│   └── adapters/
│       ├── protocols.py
│       ├── in_memory.py
│       └── postgres.py         # PostgresAlertHistoryStore + observation adapters
├── shared/                     # Lightweight shared contracts library
│   ├── __init__.py
│   ├── types.py                # Generic platform types: Entity (+ natural_key on EntityDefinition),
│   │                           #   Relationship, Alert, EvidencePack, KnowledgeBase,
│   │                           #   MonitoringObservation (used by monitoring/ and records/)
│   ├── protocols.py            # Cross-cutting protocol definitions
│   ├── alerts.py               # Alert-domain helpers
│   ├── exceptions.py           # Shared exception hierarchy
│   ├── logging.py              # structlog setup
│   ├── tracing.py              # OpenTelemetry helpers
│   ├── validation.py
│   ├── utils.py
│   └── provenance.py           # Canonical metadata-key constants for provenance fields
├── config/                     # Domain configuration
│   ├── __init__.py
│   ├── loader.py               # Reads YAML/JSON domain config; applies overlays (below) before validation
│   ├── overlay.py              # Base + environment overlay merge (ADR 0001)
│   ├── schema.py               # Pydantic DomainConfig + sub-models
│   ├── defaults/               # Complete, independently loadable domain packs
│   │   ├── medicare_fraud.yaml
│   │   ├── medicare_fraud_cms_desynpuf.yaml  # CMS DE-SynPUF + NPPES feeds (9 feeds)
│   │   ├── department_air_force_housing.yaml # DAF housing pack (6 feeds, UH/MFH scorecard templates)
│   │   └── food_supply_chain.yaml
│   └── overlays/                # Partial environment overlays (not pack-catalog packs)
│       └── medicare_fraud_dev.yaml  # dev overlay over defaults/medicare_fraud.yaml
├── events/                     # Event bus abstraction
│   ├── __init__.py
│   ├── protocols.py            # Abstract EventBus protocol
│   ├── types.py                # Event type definitions (incl. RecordsIngestedEvent)
│   ├── codec.py                # Event serialization
│   ├── runtime.py              # Bus selection / factory
│   └── adapters/
│       ├── in_memory.py
│       └── redis_streams.py
├── storage/                    # Object / file storage abstraction
│   ├── __init__.py
│   ├── protocols.py            # Abstract ObjectStore protocol
│   ├── models.py
│   └── adapters/
│       ├── in_memory.py
│       ├── local_fs_adapter.py
│       └── s3_adapter.py       # Serves both S3 and MinIO
├── database/                   # Postgres + TimescaleDB connection provider, Alembic migrations
│   ├── __init__.py
│   ├── protocols.py            # ConnectionProvider, DatabaseConnection, DatabaseCursor
│   ├── engine.py               # psycopg 3 pool-backed provider (lazy import)
│   ├── runtime.py              # create_connection_provider(config) factory
│   ├── health.py               # check_database_health(provider) readiness probe
│   ├── exceptions.py
│   └── migrations/             # Alembic env.py + versioned raw-SQL migrations
└── records/                    # Structured/tabular ingestion (CSV/JSONL/api-push), raw_records landing
    ├── __init__.py
    ├── service.py              # RecordsService.register_records(): validate → persist → publish
    ├── service_models.py       # RecordSubmission, RecordIngestReceipt (API boundary)
    ├── protocols.py            # RecordsServiceProtocol (service boundary)
    ├── models.py               # RawRecord, RecordBatch, content_hash_for
    ├── exceptions.py
    ├── validation.py           # coerce_row / validate_rows (feed schema validation)
    ├── mappers/
    │   └── feed_mapper.py      # map_batch (rows → entities/relationships), map_observations
    └── adapters/
        ├── protocols.py        # RawRecordStore, RecordSourceProtocol
        ├── in_memory.py        # InMemoryRawRecordStore
        ├── postgres.py         # PostgresRawRecordStore (raw_records table)
        └── sources/
            ├── file_source.py      # CsvFileSource, JsonlFileSource
            └── api_push_source.py  # ApiPushSource
cases/                          # Durable, KB-scoped investigation cases (BL-010)
    ├── models.py               # Case, CaseTimelineEvent
    ├── service.py              # CaseService.promote_from_alert (+ CRUD orchestration)
    ├── exceptions.py
    └── adapters/
        ├── protocols.py        # CaseRepository (create/get/list/update/delete_by_kb)
        ├── in_memory.py        # InMemoryCaseRepository
        └── postgres.py         # PostgresCaseRepository (cases table, migration 0002_cases)
policy/                         # Durable, KB-scoped policy intelligence (BL-011)
    ├── models.py               # PolicyItem, PolicyDisposition, PolicyCitation
    ├── evaluation.py           # Pure evaluate(rule_packs, state) -> list[PolicyMatch]; no I/O
    ├── service.py              # PolicyService.record_match / triage / get / list
    ├── exceptions.py
    └── adapters/
        ├── protocols.py        # PolicyItemRepository (upsert/get/list/update/delete_by_kb)
        ├── in_memory.py        # InMemoryPolicyItemRepository
        └── postgres.py         # PostgresPolicyItemRepository (policy_items table, migration 0003_policy)
scorecards/                     # Config-driven statutory scorecard runs (af_housing)
    ├── evaluation.py           # Pure evaluate_template() over SourceRecords; no I/O
    ├── service.py              # ScorecardService + ScorecardSourceRecordLoader protocol
    ├── service_models.py       # Generate/list/export request-response models
    ├── models.py               # ScorecardRun, section/metric results, export formats
    ├── exceptions.py
    └── adapters/
        ├── protocols.py        # ScorecardRunRepository
        ├── in_memory.py        # InMemoryScorecardRunRepository
        └── postgres.py         # PostgresScorecardRunRepository (migration 0008_scorecards)
conversations/                  # Durable RAG chat conversations (BL-012)
    ├── models.py               # Conversation, ConversationMessage, ConversationCitation
    ├── service.py              # ConversationService (create / get / append_messages)
    ├── exceptions.py
    └── adapters/
        ├── protocols.py        # ConversationRepository (create/get/save)
        ├── in_memory.py        # InMemoryConversationRepository
        └── postgres.py         # PostgresConversationRepository (conversations table, migration 0005_conversations)
```

> **Sprint 2026-23 additions (evidence/case vertical).**
> - **`graph.get_subgraph(kb, seed_ids, depth)`** — multi-seed neighborhood union on the graph protocol + in-memory/Neo4j adapters; the traversal primitive behind evidence-pack subgraph extraction.
> - **Evidence packs (BL-005)** are now generated for real: the worker explainability stage builds an `ExplanationContext` from `graph.get_subgraph` + risk factors/score, `ExplainabilityService` assembles the `EvidencePack`, and it is persisted (best-effort) to an object-store `EvidencePackRepository` under `analytics/explainability/`. `GET /evidence-packs/{id}` reads that repository (KB-scoped), replacing the seeded `ApiState` evidence read model.
> - **Cases (BL-010)** are durable and KB-scoped via the new `cases/` module; `POST /cases/promote` captures the originating alert + evidence pack + timeline.
>
> **Sprint 2026-24 additions (policy intelligence vertical).**
> - **Policy Intelligence (BL-011)** is durable and KB-scoped via the new `policy/` module. Domain-configured `PolicyRulePack`s are evaluated against KB entities and metrics in the worker; each hit produces a persisted `PolicyItem`. Analysts triage items (accept/reject/defer/escalate-to-case) through `POST /policy/items/{id}/triage`. The old seeded `/policy/gaps` surface, `PolicyGap*`/`PolicyBrief*` contracts, and `ApiState._seed_policy_gaps` have been removed. See [`policy/README.md`](../backend/policy/README.md).
>
> **Sprint 2026-25 additions (de-seed vertical).**
> - **De-seeded `ApiState` (BL-012).** All remaining seeded read models were moved to durable stores. Conversations are persisted via the new `conversations/` module (`ConversationRepository`, `conversations` table). `GET /graph/entities/{id}` (`api/_graph_entity_payload.py`) and `GET /analytics/overview` (`api/_analytics_overview.py`) read durable graph/risk/alert/case/KB stores. `ApiState` now owned the risk/timeseries analytics composition and the RAG service handle; its `_seed_graph`/`_seed_alerts`/`_seed_cases`/`_seed_conversations`/`_seed_evidence_packs`/`_seed_workflows` methods and the unused alert/case/conversation/evidence/workflow read methods were removed. `/admin/dev-seed` now also seeds one conversation. A regression guard asserts no non-test code reads a `_seed_*` token. **(Sprint 2026-28 B2 update, analytics.07: the timeseries half moved off `ApiState` too — see below; `ApiState` now owns only the seeded risk-score composition and the RAG service handle.)**
>
> **Sprint 2026-28 B2 additions (timeseries anomalies, API wiring — analytics.07).**
> - `GET /analytics/timeseries/{entity_id}` no longer reads `ApiState` (its seeded `_timeseries_source`/`_timeseries_service`/`get_timeseries`/`_build_timeseries_series` were deleted). It now iterates `get_entity_series_source()` — a `RecordAggregateTimeSeriesSource` over `get_record_column_source()` (`InMemoryRecordColumnSource`/`PostgresRecordColumnSource`, DI-switched on `get_connection_provider()`) and the specs in `DomainConfig.timeseries.metrics` — trying each spec's `load_series` until one has data for the entity, then joins persisted anomalies from `get_timeseries_anomaly_store()` (shipped earlier in B2). No data from any spec → `availability_status: "unavailable"`.
> - `get_timeseries_history_source()` (the separate graph-scope `/analytics/timeseries?metric=...` range route) now follows the same DI-switch pattern as `get_risk_signal_source`: `PostgresTimeSeriesHistorySource` over `entity_metric_history` when a DB is configured, else `InMemoryTimeSeriesHistorySource`.
>
> **Sprint 2026-25 additions (peer-group z-score risk signals).**
> - **`analytics/peerstats/` (BL-013–BL-015).** Config-driven cross-sectional peer-group z-score analytics. For each `PeerMetricSpec` in `DomainConfig.peer_stats`, the module aggregates a `raw_records` JSONB column per entity over a config interval (`day`/`week`/`month`), z-scores each entity against its cohort, and upserts a `DerivedRiskSignal` to the new `entity_derived_signals` table (migration `0006_entity_derived_signals`). Gated on `capabilities.peer_stats`. The worker calls `run_peerstats_stage` best-effort on every `RecordsIngestedEvent`, then assesses affected entities through the risk service. `PostgresRiskSignalSource` in `analytics/risk/adapters/postgres.py` reads `entity_derived_signals` (one signal per metric) to assemble entity risk profiles — the risk module itself is unchanged. An entity needs at least two contributing specs (≥2 derived signals) to clear the risk service's ≥2-signal floor and be scored. The medicare default config ships with two provider billing specs (`weekly_provider_billing` and `weekly_provider_claim_count`).

### 5.2 Module responsibility matrix

| Module | Owns | Depends on (via shared contracts) | Forbidden dependencies |
|--------|------|-----------------------------------|----------------------|
| `api` | HTTP routing, request validation, DI wiring, WebSocket hub | All service modules (as injected dependencies) | Must not contain business logic |
| `ingestion` | Document parsing, chunking, entity extraction | `shared.types`, `llm` (via protocol), `events` (via protocol) | `graph`, `analytics`, `api` |
| `graph` | Knowledge graph CRUD, neighborhood queries, graph metrics | `shared.types`, `shared.protocols` | `api`, `ingestion`, `analytics` |
| `vectorstore` | Embedding storage, similarity search | `shared.types` | `api`, `ingestion`, `graph` |
| `embeddings` | Text/graph-metric embedding generation | `shared.types` | `api`, `graph`, `vectorstore` |
| `rag` | RAG pipeline orchestration | `vectorstore` (protocol), `graph` (protocol), `llm` (protocol), `embeddings` (protocol) | `api`, `ingestion`, `analytics` |
| `llm` | LLM client abstraction, prompt management | `shared.types` | Everything except `shared` |
| `analytics/*` | ML/AI analysis (timeseries, GNN, risk, explainability) | `shared.types`, `graph` (protocol for reads) | `api`, `ingestion`, other analytics sub-modules |
| `analytics/metrics` | Entity-metric persistence: append history, upsert current snapshot | `database.ConnectionProvider` (Postgres adapter), `config` (backend selection) | domain logic, events, service modules |
| `analytics/peerstats` | Cross-sectional peer-group z-scores → `entity_derived_signals` upsert; gated on `capabilities.peer_stats` | `database.ConnectionProvider`, `config` (PeerMetricSpec, capability flag), `records` raw_records (via SQL, not module import) | `api`, `ingestion`, other analytics sub-modules, direct `records` imports |
| `analytics/timeseries` | Self-history anomaly detection (z-score/STL/isolation forest) → `timeseries_anomalies` upsert + `entity_derived_signals`; gated on `capabilities.timeseries` | `database.ConnectionProvider`, `config` (TimeseriesMetricSpec, capability flag), `analytics/peerstats` (`RecordColumnSourceProtocol`, reused aggregate SQL) | `api`, `ingestion`, other analytics sub-modules |
| `agent` | Pipeline coordination, state machine | `events` (protocol), `shared.types` | Direct imports of service internals |
| `monitoring` | Stream consumption, alert generation | `shared.types`, `events` (protocol) | `api`, `ingestion` internals |
| `knowledgebases` | KB/document metadata persistence, repository adapters, projection snapshots | `shared.types`, `storage` (protocol) | `api`, `ingestion`, `graph`, `vectorstore` internals |
| `conversations` | Durable chat conversation/message persistence and retrieval | `shared.types`, `database.ConnectionProvider` | `api`, `rag`, `llm` internals |
| `shared` | Domain types, protocols, utilities | Python stdlib only | Everything — must be leaf dependency |
| `config` | Configuration loading and validation | `shared.types` | Everything except `shared` |
| `events` | Event bus abstraction; durable DLQ ledger (`DlqRecordStore`, BL-023) | `shared.types`, `database.ConnectionProvider` (Postgres DLQ adapter) | Everything except `shared`, `database` |
| `storage` | Object/file storage abstraction | `shared.types` | Everything except `shared` |
| `database` | Connection pooling, schema migrations | `config`, `shared` | domain logic, business logic, imports of any capability module |
| `records` | Structured-record validation, raw_records persistence, feed mapping | `config`, `shared`, `events`, `database`, `monitoring.models` | imports of `graph`/`analytics` internals — communicates downstream only by publishing `RecordsIngestedEvent` |
| `policy` | KB-scoped policy item persistence, rule evaluation, analyst triage | `config` (PolicyRulePack), `shared.types`, `database.ConnectionProvider` | `api`, `ingestion`, `graph` internals — the pure `evaluate()` function takes a plain `PolicyEvalState`; item I/O goes through `PolicyItemRepository` |
| `cases` | KB-scoped investigation case management | `shared.types`, `database.ConnectionProvider` | `api`, `ingestion`, `monitoring` internals |
| `scorecards` | Config-driven scorecard evaluation (`evaluate_template`), durable run persistence, JSON/Markdown exports | `config` (ScorecardTemplateConfig), `shared`, `database.ConnectionProvider`; feed records arrive through the `ScorecardSourceRecordLoader` protocol implemented at the gateway | `records`, `api`, `ingestion` internals — never imports the records module directly |

### 5.3 Cross-module interaction rules

The following diagram illustrates the three permitted interaction paths:

```
                         ┌──────────────┐
              Path A     │              │     Path A
           ┌────────────▶│   api/       │◀────────────┐
           │  (HTTP)     │  (FastAPI)   │   (HTTP)    │
           │             └──────┬───────┘             │
           │                    │ injects              │
    ┌──────┴──────┐    ┌───────▼────────┐    ┌───────┴──────┐
    │ ingestion   │    │   agent/       │    │   rag        │
    │             │    │  (coordinator) │    │              │
    └──────┬──────┘    └───────┬────────┘    └──────┬───────┘
           │          Path B   │                    │
           │         (events)  │                    │
           ▼                   ▼                    ▼
    ┌─────────────────────────────────────────────────────┐
    │                    events/                           │
    │               (Redis Streams)                       │
    └──────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ graph    │ │analytics │ │monitoring│
        └──────────┘ └──────────┘ └──────────┘

                  Path C: all modules import from
              ┌──────────────────────────────────┐
              │         shared/                  │
              │  (types, protocols, utilities)   │
              └──────────────────────────────────┘
```

**Path A — FastAPI gateway orchestration**

The API layer receives a frontend request, validates it, and calls the appropriate service module(s) through injected dependencies. The service modules never call back into the API layer.

Example: `POST /knowledgebases/{id}/documents` → API router calls `ingestion.process()`, then publishes a `documents.uploaded` event.

**Path B — Agent / workflow coordinator orchestration**

The agent module coordinates multi-step pipelines by publishing and subscribing to events. Individual service modules react to events independently — they do not know about each other.

Example: Agent publishes `ingest.start` → Ingestion worker processes documents → publishes `entities.extracted` → Graph builder consumes and upserts → publishes `graph.updated` → Analytics consumes and processes → publishes `risk.scored` / `explainability.generated` → Alert service evaluates and publishes `alerts.created`.

**Path C — Shared contracts library**

Modules share stable type definitions, protocol interfaces, and small utilities through the `shared` package. This package must remain dependency-light and must never contain business logic.

Example: `shared.types.Entity` is used by `ingestion` (produces entities), `graph` (stores entities), and `analytics` (reads entities).

---

## 6. Data Flow & Pipeline Architecture

### 6.1 Flow A — Knowledge Base Creation (batch)

This flow is triggered when an analyst creates a new knowledge base and uploads policy documents.

```
Analyst                 API                 Redis              Workers
  │                      │                   │                   │
  │  POST /knowledgebases│                   │                   │
  │─────────────────────▶│                   │                   │
  │                      │  XADD             │                   │
  │                      │  kb.create        │                   │
  │                      │──────────────────▶│                   │
  │  201 Created         │                   │                   │
  │◀─────────────────────│                   │                   │
  │                      │                   │  XREADGROUP       │
  │                      │                   │  kb.create        │
  │                      │                   │──────────────────▶│
  │                      │                   │                   │
  │  POST /knowledgebases│/{id}/documents    │                   │
  │─────────────────────▶│                   │                   │
  │                      │  Upload to        │                   │
  │                      │  object store     │                   │
  │                      │  XADD             │                   │
  │                      │  docs.uploaded    │                   │
  │                      │──────────────────▶│                   │
  │  200 OK              │                   │                   │
  │◀─────────────────────│                   │                   │
  │                      │                   │                   │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Ingestion    │ │
  │                      │                   │  │ • Parse docs │ │
  │                      │                   │  │ • Chunk text │ │
  │                      │                   │  │ • Extract    │ │
  │                      │                   │  │   entities & │ │
  │                      │                   │  │   relations  │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │◀────────┘         │
  │                      │                   │  XADD             │
  │                      │                   │  entities.extracted│
  │                      │                   │                   │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Graph Builder │ │
  │                      │                   │  │ • Upsert     │ │
  │                      │                   │  │   entities   │ │
  │                      │                   │  │ • Upsert     │ │
  │                      │                   │  │   relations  │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Embedder     │ │
  │                      │                   │  │ • Embed text │ │
  │                      │                   │  │ • Embed graph│ │
  │                      │                   │  │   metrics    │ │
  │                      │                   │  │ • Store in   │ │
  │                      │                   │  │   vector DB  │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │◀────────┘         │
  │                      │                   │  XADD             │
  │                      │                   │  kb.ready         │
  │                      │                   │                   │
  │  WS: kb.ready        │                   │                   │
  │◀═════════════════════│◀──────────────────│                   │
```

### 6.2 Flow B — Active Monitoring & Analysis (streaming + batch)

This flow runs continuously once a knowledge base is active and monitoring is enabled.

```
Data Source             API / Feed          Redis              Workers
  │                      │                   │                   │
  │  Claims / records    │                   │                   │
  │─────────────────────▶│                   │                   │
  │                      │  XADD             │                   │
  │                      │  claims.received  │                   │
  │                      │──────────────────▶│                   │
  │                      │                   │                   │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Ingestion    │ │
  │                      │                   │  │ • Parse      │ │
  │                      │                   │  │ • Normalize  │ │
  │                      │                   │  │ • Extract    │ │
  │                      │                   │  │   entities   │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │◀────────┘         │
  │                      │                   │  XADD             │
  │                      │                   │  claims.ingested  │
  │                      │                   │                   │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Graph Builder │ │
  │                      │                   │  │ • Update     │ │
  │                      │                   │  │   claims     │ │
  │                      │                   │  │   graph      │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │◀────────┘         │
  │                      │                   │  XADD             │
  │                      │                   │  graph.updated    │
  │                      │                   │                   │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Analytics    │ │
  │                      │                   │  │ Pipeline     │ │
  │                      │                   │  │              │ │
  │                      │                   │  │ ┌──────────┐ │ │
  │                      │                   │  │ │TimeSeries│ │ │
  │                      │                   │  │ │ anomaly  │ │ │
  │                      │                   │  │ │ detection│ │ │
  │                      │                   │  │ └────┬─────┘ │ │
  │                      │                   │  │      ▼       │ │
  │                      │                   │  │ ┌──────────┐ │ │
  │                      │                   │  │ │   GNN    │ │ │
  │                      │                   │  │ │ link pred│ │ │
  │                      │                   │  │ │clustering│ │ │
  │                      │                   │  │ └────┬─────┘ │ │
  │                      │                   │  │      ▼       │ │
  │                      │                   │  │ ┌──────────┐ │ │
  │                      │                   │  │ │  Risk    │ │ │
  │                      │                   │  │ │ Scorer   │ │ │
  │                      │                   │  │ └────┬─────┘ │ │
  │                      │                   │  │      │       │ │
  │                      │                   │  └──────┼───────┘ │
  │                      │                   │         │         │
  │                      │                   │◀────────┘         │
  │                      │                   │  XADD             │
  │                      │                   │  risk.scored      │
  │                      │                   │                   │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Results      │ │
  │                      │                   │  │ • Enrich     │ │
  │                      │                   │  │   graph with │ │
  │                      │                   │  │   scores     │ │
  │                      │                   │  │ • Build      │ │
  │                      │                   │  │   evidence   │ │
  │                      │                   │  │   packs      │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │  ┌──────────────┐ │
  │                      │                   │  │ Alert        │ │
  │                      │                   │  │ Service      │ │
  │                      │                   │  │ • Evaluate   │ │
  │                      │                   │  │   thresholds │ │
  │                      │                   │  │ • Generate   │ │
  │                      │                   │  │   alerts     │ │
  │                      │                   │  └──────┬───────┘ │
  │                      │                   │         │         │
  │                      │                   │◀────────┘         │
  │                      │                   │  XADD             │
  │                      │                   │  alerts.created   │
  │                      │                   │                   │
  │                      │  WS: alerts       │                   │
  │              Analyst◀═══════════════════◀│                   │
```

### 6.3 Flow 1 — Structured Record Ingestion

This flow handles tabular feeds (CSV/JSONL file uploads, JSON api-push) submitted through the records API. It is parallel to Flow A (document ingestion) but targets the `raw_records` table rather than the document pipeline.

```
Data source (CSV / JSONL / api-push)
  │
  │  POST /records/{knowledge_base_id}/files
  │  POST /records/{knowledge_base_id}/push
  ▼
RecordsService.register_records()
  • Resolve feed config (DomainConfig.records.feeds)
  • validate_rows(): coerce types, check against feed schema
  • Build RawRecord list with content_hash (idempotency digest)
  │
  ▼
RawRecordStore.persist()             # raw_records table (idempotent upsert)
  │
  ▼
publish RecordsIngestedEvent
  │
  ▼ (Redis Streams → worker)
handle_records_ingested()
  ├── map_batch()  → GraphService.upsert_records_graph()
  │                   # entities + relationships, no document artifacts,
  │                   # no GraphUpdatedEvent published
  ├── map_observations() → PostgresObservationStore.write_observations()
  │                           # observations table (idempotent upsert)
  ├── run_peerstats_stage()   # best-effort, gated on capabilities.peer_stats
  │     │
  │     └── PeerStatsService.compute()
  │           • PostgresRecordColumnSource aggregates raw_records JSONB per entity/interval
  │           • population z-score per entity vs peer cohort (same entity_type + interval)
  │           • map z → [0,1] signal value (direction, z_cap)
  │           • PostgresDerivedRiskSignalWriter.upsert() → entity_derived_signals
  ├── run_timeseries_stage()  # best-effort, gated on capabilities.timeseries; independent of peerstats
  │     │
  │     └── for each TimeseriesMetricSpec matching this feed's record_type:
  │           • load_entity_series_map() (RecordAggregateTimeSeriesSource) — one aggregate
  │             query per spec, reusing the peerstats RecordColumnSourceProtocol SQL
  │           • TimeseriesService.analyze() per entity (self-history z-score / STL / isolation forest)
  │           • PostgresTimeseriesAnomalyStore.write_anomalies() → timeseries_anomalies
  │           • latest anomaly per entity → DerivedRiskSignal (metric_name
  │             `timeseries_anomaly:<spec name>`) → entity_derived_signals
  ├── for each entity affected by either stage (deduped):
  │     RiskService.assess()
  │       # PostgresRiskSignalSource assembles signal profile
  │       # (latest signal per metric from entity_derived_signals)
  │       # → risk_score_history + graph entity snapshot
  └── records→analytics fan-out (analytics.34; gated on
        DomainConfig.records.analytics_trigger, per-KB throttle window,
        top-N assessed entities by overall_score):
        handle_graph_updated_for_analytics()   # DIRECT in-process call —
          # an in-memory GraphUpdatedEvent with inline upserted_entity_ids;
          # never published, so Flow A (embeddings) does not re-run and no
          # storage-key artifacts are staged. Best-effort: a failure here
          # publishes analysis.failed (stage=analytics_fanout) and never
          # replays the ingest via retry/DLQ.
```

Every write is an idempotent upsert keyed on `(knowledge_base_id, record_type, record_id)` for `raw_records`, on `(entity_id, metric_name, observed_at)` for `observations`, on `(knowledge_base_id, entity_id, metric_name, interval_start)` for `entity_derived_signals`, and on `(knowledge_base_id, entity_id, metric_name, observed_at)` for `timeseries_anomalies`, so the worker's retry/DLQ wrapper can re-run the handler safely without duplicating data.

`GraphService.upsert_records_graph` is the records-specific graph entry point. Unlike the document pipeline's `upsert_graph`, it accepts no document artifacts and does not publish a `GraphUpdatedEvent` — Flow B analytics for records KBs instead run via the gated in-process fan-out at the end of `handle_records_ingested` (analytics.34), which needs no published event and no artifacts. The `observations` table has a write-side adapter at `monitoring/adapters/postgres.py` (`PostgresObservationStore`). The `entity_derived_signals` table is written by `PostgresDerivedRiskSignalWriter` (`analytics/peerstats/adapters/postgres.py`) and read by `PostgresRiskSignalSource` (`analytics/risk/adapters/postgres.py`) when assembling entity risk profiles. The peerstats and timeseries stages each run independently and best-effort — a failure in one no longer skips the other or risk assessment for entities the other stage did affect; risk assessment runs once per entity across the union of both stages' affected ids. Extreme flat-baseline z-scores (`z=inf`) are clamped to `1e6` before being persisted so stored floats stay JSON-safe.

### 6.4 Plan C Persistence Flows (worker-side write-back)

These three flows run in the worker (`agent/coordinator.py`) and form the **persistence backbone** that durably records analytics results to Postgres/TimescaleDB. The per-consumer Postgres adapters (`monitoring/adapters/postgres.py::PostgresObservationSource`, `analytics/timeseries/adapters/postgres.py::PostgresTimeSeriesHistorySource`, `analytics/risk/adapters/postgres.py::PostgresRiskHistoryStore`, `analytics/metrics/adapters/postgres.py::PostgresEntityMetricRepository`, and `monitoring/adapters/postgres.py::PostgresAlertHistoryStore`) are now the implemented read/write side of this backbone.

**Flow 2 — Graph metric persistence** (`handle_graph_updated_for_analytics`)

Triggered by `GraphUpdatedEvent`. Computes graph-scope metrics (entity count, relationship count, avg degree) from the graph service and writes them to `entity_metric_history` (TimescaleDB hypertable, append) and `entity_metrics_current` (upsert). Throttled per knowledge-base by `MetricsRecomputeThrottle` (configurable interval, default 300 s) to prevent recompute storms from bursts of `GraphUpdatedEvent`s.

**Flow 3 — Risk score persistence** (`handle_risk_scored_for_graph`)

Triggered by `RiskScoredEvent`. Writes the full risk assessment to `risk_score_history` for durable audit. Also snapshots `risk_score`, `risk_level`, and `risk_assessed_at` as properties onto the affected graph entities so investigation queries can read current scores from the graph without a SQL join (the graph snapshot is a best-effort denormalized cache; `risk_score_history` is authoritative).

**Idempotency + failure durability.** Each assessment carries a deterministic `request_id = risk:{correlation_id}:{kb}:{entity}` (set by the worker fan-out / peerstats stage via `RiskAssessmentRequest.request_id`). That id keys `risk_score_history` (`ON CONFLICT(request_id) DO NOTHING`), the monitoring batch (`handle_risk_scored` uses it as `batch_id`), and the derived `alert_id` — so a **retried** assessment of the same triggering event dedups instead of accumulating duplicate rows, while a genuinely new event (new `correlation_id`) still appends. Because the chain is idempotent, the dispatch no longer swallows the `RiskScoredEvent`/`AlertsCreatedEvent` write-backs: a transient DB/event-bus failure in `risk_score_history`/`alert_history` now **propagates to the retry/DLQ wrapper** rather than being silently dropped. (Monitoring and the graph snapshots remain best-effort. The `GraphUpdatedEvent` Flow-B analytics fan-out is still wrapped best-effort so it cannot re-run Flow A's embeddings on retry; splitting Flow B into its own retryable consumer is tracked as follow-up.)

**Flow 4 — Alert persistence** (`handle_alerts_created_for_graph`)

Triggered by `AlertsCreatedEvent`. Writes each alert to `alert_history` for durable audit. Also snapshots `active_alert_count`, `last_alert_at`, and `last_alert_severity` onto the affected graph entities. The row's read-model columns (`entity_label`/`confidence`/`tags`, alerts.36) are populated by whichever producer built the `AlertCreatedReference`: the analytics pipeline's `_run_explainability_stage` sets `confidence` from the risk assessment's `overall_score` and `tags` from the top-3 risk-factor names (kebab-cased), falling back `entity_label` to `entity_id` (no cheap display value is in scope without an extra graph read); `MonitoringService.evaluate()` sets `confidence` from the alert candidate's threshold-ratio score and `tags` from a kebab-slugged `metric_name`, leaving `entity_label` at its `""` default (monitoring observations carry no display name). All three fields default (`""`/`0.0`/`[]`) so a legacy serialized `AlertCreatedReference` predating alerts.36 still decodes.

**Flow 5 — Document status projection** (BL-041)

Every drained ingestion event passes through the worker's `_dispatch_event` (`agent/coordinator.py`), which calls `agent.status_projection.project_document_status(event, document_status_store)` before/alongside its existing handler dispatch. `project_document_status` maps four subscribed event types onto a monotonic `IngestionStatus` transition per document and applies it via `SourceDocumentStatusStore.apply()`:

| Event | Status transition |
|---|---|
| `DocumentsUploadedEvent` | `PENDING` |
| `DocumentsParsedEvent` | `PARSED` |
| `DocumentsFailedEvent` | `FAILED` (carries `error_message`) |
| `DocumentsExtractionWarningEvent` | `EXTRACTED_EMPTY` when `document.empty_extraction` is `True`, else `VALIDATED` (carries drop counts + bounded `sample_reasons`) |

`EXTRACTED_EMPTY` is a status value only — no new event type was introduced, so the hand-maintained event codec registry (`events/codec.py`) is untouched. The store's `apply()` is monotonic on `STATUS_RANK` (`ingestion/models.py`): a transition only advances `current_status` when its rank is strictly greater than the stored rank, so out-of-order or redelivered events (e.g. a stale `PARSED` arriving after `FAILED`) are no-ops. `last_error` is the one field that also refreshes on a same-or-higher-rank `FAILED` redelivery (so a second, newer failure message replaces the first), while a lower-rank event after `FAILED` never touches it. Drop counts and `sample_reasons` are absolute values that overwrite whenever the transition carries them, independent of rank. Both the in-memory (`ingestion/adapters/in_memory.py`) and Postgres (`ingestion/adapters/postgres.py`, `source_document_status` table via migration `0009_document_status`) adapters implement identical semantics — the Postgres adapter enforces them with a single `INSERT … ON CONFLICT DO UPDATE` guarded by `CASE`/`GREATEST` expressions rather than a read-then-write race. `GET /knowledgebases/{kb_id}/documents` reads this projection (`current_status`, `last_error`, drop counts, `drop_sample_reasons`) per document and supports `?status=` filtering; KB deletion purges the projection via `delete_by_kb`, and single-document deletion / changed-content reupload purge the superseded row via `delete_by_document` (§7.1 carries the full KB-cascade detail).

#### Worker loop resilience + health honesty

The `run_worker` loop wraps each drain iteration (workflow reconcile + `drain_ingestion_events`) in a resilience guard: a transient failure (e.g. a Redis outage in `consume`/`ack`, or the reconcile) is recorded, logged, and followed by a short backoff (`DRAIN_ERROR_BACKOFF_SECONDS`) before continuing — it never crashes the worker process (only `CancelledError` ends the loop, for graceful shutdown). The drain itself is factored into `_drain_once` so the loop body stays small enough to guard.

The worker `/health` endpoint reports honestly. `HealthState` distinguishes a **successfully processed** event from a **dead-lettered** one: a delivery whose retries are exhausted and routed to the DLQ calls `mark_event_dead_lettered()` (not `mark_event_processed()`), so a worker dead-lettering 100% of events no longer looks `"ok"`. `status()` returns `"degraded"` when (a) consecutive drain errors reach `degraded_after_drain_errors` (default 3), (b) events have been received but every one was dead-lettered (no successful progress), or (c) the worker was processing and has since stalled past `degraded_after_seconds`. A freshly-started, idle worker with no errors is genuinely `"ok"`. The payload also surfaces `events_processed`, `events_dead_lettered`, `consecutive_drain_errors`, and `last_drain_error` for operators.

#### Workflow submission + cooperative cancellation

Workflow runs are created intentionally by `AgentService.start_workflow`, wired into the two pipeline entry points in the API gateway (`POST /knowledgebases/{kb}/documents` → `documents.uploaded`; `POST /records/{kb}/files`|`/push` → `records.ingested`). The route threads the run's `correlation_id` into the published event, and `start_workflow` is **create-or-get by correlation id**, so it converges with any fallback run the worker's `WorkflowEventTracker` minted in a race (no duplicates). The tracker fallback is retained as a safety net; `agent.workflow_tracking.default_steps_for_trigger` is the single source of truth for step plans. The `WorkflowRunStore` keeps a `correlation_id → workflow_id` index (`find_by_correlation_id`) so resolution is O(1), not a scan. Because the run is created synchronously at submit, `ensure_kb_idle` enforces **one ingestion workflow per KB at a time** (a second mutation while non-terminal → 409); API and worker must share the run store (`CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`).

Cancellation (`POST /workflows/{id}/cancel`, analyst role) is **cooperative**: the tracker skips a cancelled run's remaining steps at each event boundary; long handlers (`handle_graph_updated_for_analytics`, `handle_records_ingested`) re-check `is_run_cancelled` at loop/stage boundaries and stop early (an in-flight synchronous stage still finishes); and tracker writes use a status-only CAS (`update_run_if_current` with `expected_statuses={QUEUED, RUNNING}`) so a concurrent cancel is never clobbered.

#### Plan C design deviations

The following decisions were made during Plan C implementation and differ from the original design intent:

- **Risk adapter is writer-only for history; `PostgresRiskSignalSource` reads derived signals**: `PostgresRiskHistoryStore` is a write-side adapter plus `load_historical_score` (point read). Risk signal assembly now has a Postgres-backed read path via `PostgresRiskSignalSource` (`analytics/risk/adapters/postgres.py`), which reads `entity_derived_signals` (populated by `analytics/peerstats/`) to build entity risk profiles when the `peer_stats` capability is enabled.
- **Entity-property snapshot instead of graph history nodes**: Flows 3 and 4 write a flat entity-property snapshot to the graph (e.g., `risk_score`, `active_alert_count`) alongside full history in SQL tables. Graph-native "history nodes" (linking graph entities to historical result nodes inside the graph DB) are deferred.
- **Flow 2 throttled per-KB**: Metric recompute is rate-limited per knowledge-base to avoid redundant work on ingest bursts. The interval is configurable via `analytics.metrics_recompute_min_interval_seconds` (default 300 s) in the domain config.

### 6.5 Ingestion Pipeline Enhancements (2026-05-22)

The following additions landed in `feature/ingestion-pipeline-e2e-demo`. See the full design at [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md).

**LLM extractor + Ollama adapter**

`LlmDocumentExtractor` in `ingestion/extractor.py` drives entity/relationship extraction from schema-guided prompts derived from `DomainConfig.entities` / `DomainConfig.relationships`. It requests JSON-mode responses, strips markdown fences, validates required properties, and deduplicates entities by natural key within each chunk. Extractor selection lives in `agent.coordinator.build_document_extractor`: every real provider routes extraction through `LlmDocumentExtractor`; `llm.provider="local"` (the deterministic echo stub) keeps the `PatternDocumentExtractor` baseline. Before schema validation, `ingestion/normalization.py` coerces raw property values to their configured types (string decimals → float, regional dates → ISO 8601, yes/no → bool, enum casing), so string-valued sources like CSV records survive `validate_entity`. Per-document parse and extraction warnings are persisted to `DocumentRecord` (`record_document_warnings`) and exposed via `DocumentSummary.warning_count`/`warning_reasons` for the Ingestion Studio.

`OllamaLlmClient` in `llm/adapters/` is a new adapter implementing `LlmClientProtocol` via Ollama's OpenAI-compatible endpoint. It is selected by `LlmConfig.provider="ollama"` with `LlmConfig.base_url` pointing at the Ollama host. `FallbackLlmClient` wraps a primary client with an ordered list of fallback clients tried on error.

**Optional PDF OCR fallback** — OCR is a supported **optional** adapter behind the `OcrAdapterProtocol` (`ingestion/parsers/protocols.py`): when a `PdfParser` is constructed with an `ocr_adapter` (e.g. `TesseractOcrAdapter`, behind the `[ocr]` extra), pages that yield no extractable text are OCR'd page-by-page and stamped `parser_metadata["ocr_used"]=True`; it is opt-in per deployment and the default (no adapter) keeps the unchanged "text-less PDF → `ParserError`" behavior (`ingestion.03`).

**Provenance metadata on entities and relationships**

Every `Entity` and `Relationship` produced by the document pipeline now carries provenance fields:

| Field | Source |
|-------|--------|
| `source_kind` | `"document"` for text-derived chunks or `"record"` for structured-record chunks — stamped by the validator from each chunk's origin (`ChunkMetadata.source_kind`), so records ingested through the document pipeline via `StructuredRecordChunker` are correctly `"record"`, not just those from the records pipeline |
| `source_document_id` | SHA-256 of source content |
| `source_chunk_id` | Chunk index within the document |
| `source_feed` | Feed name (records-derived only) |
| `source_raw_record_id` | Raw record ID (records-derived only) |

**KB delete cascade (207 sequence) + workflow-busy 409 guard**

`DELETE /knowledgebases/{id}` executes a complete cascade across **every** per-KB durable store, then deletes KB repository metadata. The single authoritative ordered step list is `knowledgebases.cleanup.kb_deletion_steps` (operating on a `knowledgebases.cleanup.KbDeletionStores` bundle): graph namespace (`GraphService.delete_knowledge_base`), vector namespace (`VectorService.delete_knowledge_base`), `raw_records` + `record_submissions` (`RawRecordStore.delete_by_kb`), peerstats `entity_derived_signals`, timeseries anomalies (`timeseries_anomalies` step, `TimeseriesAnomalyPurger.delete_by_kb` — analytics-owned, required in **both** bundles; positioned directly after the derived-signals step), `risk_score_history`, `observations`, `alert_history` (`AlertHistoryWriter.delete_by_kb` — this single step now purges the durable alert feed too, since the API serves alerts directly off `alert_history` rather than a separate read projection; **alerts.36** retired the API-owned `alert_projection` step), GNN cluster summaries (`gnn_clusters` step, `GnnClusterPurger.delete_by_kb` — analytics-owned, required in **both** bundles; API and worker each construct their own `ObjectStoreClusterSummaryStore` from the injected object store), `entity_metric_history` + `entity_metrics_current`, `conversations`, `cases`, `policy_items`, evidence packs, scorecard runs (each via its repository's `delete_by_kb`), the document-status projection (`SourceDocumentStatusStore.delete_by_kb`), and object-store payloads. The API assembles the bundle from DI (`api._kb_cleanup.get_kb_deletion_stores`) and each step runs best-effort (`_run`); any failure surfaces in the 207 body and flags the KB `pending_cleanup`. On a 207, the worker consumes the `KnowledgeBaseDeletedEvent(cleanup_pending=True)` and **replays the same `kb_deletion_steps`** (its bundle built in `build_worker_dependencies`), then deletes KB metadata once every store is purged — so the cascade lives in exactly one place and the sync + retry paths can never diverge. If an active workflow run exists for the KB at delete time the API returns 409 to prevent mid-pipeline teardown.

`GraphService` and `VectorService` additionally expose `delete_by_source_document(kb_id, doc_id)` for document-level (rather than KB-level) provenance cleanup. `SourceDocumentStatusStore` similarly exposes `delete_by_document(kb_id, doc_id)`, called from the single-document delete endpoint so a status-filtered `GET .../documents?status=...` list's `total` never outlives the document it counted. Because an in-flight pipeline event can still re-create a status row for an already-deleted document (an orphan resurrection race), the status-filtered listing itself defends against this: it excludes any row with no matching registered document from both `items` and `total` and opportunistically reaps it via `delete_by_document`, so an orphan never permanently inflates `total`.

**Document re-upload semantics**

Re-uploading a document with identical content bytes is idempotent (same `source_document_id`, no duplicate event). Re-uploading changed content produces a new `source_document_id`; the receipt includes a `replaced_document_id` field pointing at the superseded entry.

**New NPPES and DE-SynPUF feeds (medicare_fraud config)**

`config/defaults/medicare_fraud_cms_desynpuf.yaml` now declares nine feed definitions under `records.feeds`: `nppes_providers`, `beneficiary_2008`, `beneficiary_2009`, `beneficiary_2010`, `carrier_claims_a`, `carrier_claims_b`, `inpatient_claims`, `outpatient_claims`, and `pde`. These are config-only additions — the records pipeline code is unchanged. A Tennessee-provider subset materializer lives at `tools/sample_data/build_tennessee_subset.py` and is invoked by the `make demo-tn-subset` target.

`handle_records_ingested` in the worker now also embeds and indexes records-derived entities into the vector store so they are co-searchable with document-derived content in RAG queries.

### 6.6 Policy Intelligence flow (BL-011)

Policy items are generated from domain-configured rule packs and surfaced for analyst triage. The flow is best-effort and KB-scoped.

```
DomainConfig.policy_rules
  (list[PolicyRulePack])
       │
       │  loaded at startup via DI
       ▼
handle_records_ingested()          ← triggered by RecordsIngestedEvent
  │
  ├── evaluation.evaluate(rule_packs, PolicyEvalState(entities, metrics))
  │     # pure function; no I/O; returns list[PolicyMatch]
  │
  └── for each PolicyMatch:
        PolicyService.record_match(...)
          └── PolicyItemRepository.upsert(item)
                # natural key (kb_id, rule_id, target_ref)
                # open items refreshed; disposed items untouched

                          ┌──────────────────────┐
                          │  PolicyItem (open)    │
                          └────────┬─────────────┘
                                   │  POST /policy/items/{id}/triage
                         ┌─────────┴─────────────────────────┐
                         │                                   │
                   accept / reject / defer            escalate
                         │                                   │
                 PolicyDisposition stored          PolicyDisposition stored
                 status → accepted/rejected/       status → escalated
                         deferred                  CaseService.create() called
                                                   (additive timeline param)
```

**Deviations recorded at implementation time:**

- **D-EVAL-IMPL**: evaluation is folded into `handle_records_ingested` (no standalone pipeline stage). Alert-target rules (`target_kind = "alert"`) are parsed but not yet evaluated.
- **D-ESCALATE-IMPL**: escalate-to-case uses `CaseService.create(timeline=...)` directly, not the `POST /cases/promote` alert→case path.
- **D-DISPOSITION-JSONB**: `PolicyDisposition` is stored as a jsonb column (not a separate table).

### 6.7 Self-reinforcing analysis loop

The analytics pipeline is designed as a **feedback loop**: analysis results (risk scores, cluster memberships, anomaly flags) are written back to the knowledge graph, enriching it for subsequent analysis rounds. This means:

- GNN link prediction benefits from risk scores computed in previous rounds
- Time-series anomaly detection can incorporate graph-derived features
- Risk scoring aggregates signals from both time-series and GNN outputs
- Each monitoring cycle produces a progressively richer graph

**What's implemented today (Sprint 2026-28 B1).** The GNN half of this loop is live, not fixture-only, on two independent paths that read from the same in-flight `GnnAnalysisResult` (both best-effort — a store failure logs a warning and never fails the pipeline):
1. **Per-entity graph properties.** `agent.coordinator._write_analytics_properties_to_graph` (Flow B, right after the risk stage) writes `community_id` and `centrality_score` onto each upserted entity alongside `risk_score`/`risk_level` — so a graph query or export sees GNN structure inline with risk. This existed before B1; B1 only verified and documented it.
2. **Per-KB cluster summaries.** `agent.coordinator._persist_gnn_clusters` (Flow B, immediately after the GNN stage) writes one `ClusterSummary` per detected community to a `ClusterSummaryStoreProtocol` (`analytics/gnn/adapters/cluster_store.py`; object-store-backed in the API/worker, in-memory for tests), so `GET /analytics/gnn/clusters` (`GnnService.list_clusters`) serves the latest real pipeline output instead of only whatever a test seeded — see § "Analytics Runtime Notes" in `backend/README.md`.

The snapshot side of the loop is also live: `GraphRepositorySnapshotSource` (`analytics/gnn/adapters/graph_repository_source.py`) loads nodes/edges for `GnnService.analyze` from the real configured `GraphRepository` (in-memory or Neo4j), bounded by `DomainConfig.gnn.snapshot_max_nodes` (top-degree nodes kept). `backend/tests/analytics/gnn/test_gnn_live_integration.py` (`@pytest.mark.integration`) proves the round trip end to end against a live Neo4j instance: seed entities/relationships → load a snapshot → `analyze()` → scored nodes + communities.

**Not yet implemented:** `predicted_links` (GNN link predictions) are computed by `analyze()` but never written back to the graph or persisted anywhere durable — only the scored/community half of the loop closes today. Time-series anomaly flags are not written back to the graph either. Both gaps are tracked in `docs/backlog/analytics.md` (analytics.24, analytics.25).

### 6.8 Housing scorecards & executive dashboard (branch `af_housing`)

The Department of the Air Force housing demo exercises the platform's domain-reconfigurability with a statutory-reporting vertical. Every piece is configured or generic — no housing types are hardcoded.

**Scorecards module (`backend/scorecards/`).** A standard-shape module that evaluates config-driven report templates. `evaluation.py` is pure (no I/O): `evaluate_template()` grades `ScorecardTemplateConfig` metrics against `SourceRecord` rows, applying bounded formula operators (`ratio`, `sum`, `mean`, `weighted_mean`, `latest`), per-metric freshness windows, and threshold banding. `ScorecardService.generate()` selects the KB's records by scope + period, evaluates, content-hashes the source snapshot into the run id, and persists the `ScorecardRun` through `ScorecardRunRepository` (in-memory or Postgres, migration `0008_scorecards`). Runs export as JSON or Markdown.

**Threshold directions.** `ScorecardThresholdConfig` supports exactly one grading direction per metric: higher-is-better (`pass_min`/`warn_min`/`fail_max`) or lower-is-better (`pass_max`/`warn_max`/`fail_min`). Mixing directions is a load-time validation error, and bounds must be ordered so grading bands cannot overlap.

**`RecordFeedSourceLoader` bridge (`api/dependencies.py`).** Scorecards never import the records module. The gateway implements the `scorecards.service.ScorecardSourceRecordLoader` protocol with `RecordFeedSourceLoader`, which reads the raw-record store (`RawRecordStore.load_for_kb`), maps stored `record_type`s back to the active config's feed names, and dates each row from its `snapshot_date` column so freshness checks operate on real observation dates. This keeps the cross-module interaction on the sanctioned gateway path.

**Housing read models (`api/_housing_read_model.py` + `api/routers/housing.py`).** The `/housing/overview` and `/housing/installations` endpoints are a thin router over gateway read-model builders (the same extraction pattern as `api/_analytics_overview.py`). The builders aggregate the KB's ingested feed rows — the same rows the scorecard evaluator consumes via the bridge — into per-installation rollups, derive `ok`/`watch`/`critical`/`unknown` status with statutorily informed banding, and default to the newest KB of the active domain when no `knowledge_base_id` is passed. `derive_status_with_reasons` is the single threshold evaluation: it returns the status band **and** the human-readable `status_reasons` the API exposes per installation (`derive_status` is a thin wrapper), so the band and its explanation can never disagree — including at boundary values. Installations also carry `open_work_orders_rank`, a competition rank computed among *reporting* installations only (non-reporters are `unknown` and unranked). Each installation row additionally exposes the aggregate inputs behind every overview number — value/weight pairs (`occupancy_rate`/`occupancy_unit_weight`, `condition_index`/`condition_unit_weight`, `resident_satisfaction`/`satisfaction_survey_count`), work-order counts, and UH/MFH available-vs-authorized units (nullable where the feed never reported) — taken from the same rollup accumulators the overview sums, so the frontend can recompute every portfolio aggregate for any filtered subset with identical semantics (the exact formulas are documented on the contract fields and pinned by exact-equality router tests). Note the two weights differ by design: occupancy weighs by total units (available + offline) of utilization-reporting rows; condition weighs by available units of condition-reporting rows. Installations without resolvable coordinates appear in `items` but not `map_points`; the frontend renders them as a visible "location pending" list rather than dropping them.

**Frontend.** `/housing` (`HousingExecutivePage`) renders a real Albers CONUS map (`d3-geo` + `topojson-client` + pre-projected `us-atlas` states, no tile servers) with all 65 CONUS AF/SF installations, marker declutter with leader legs, branch glyphs (USAF/USSF), and status/size encodings. A single summary band (`HousingSummaryBand`) sits **above the map** (header → band → filter strip → map → ranking) and carries every portfolio aggregate — counts plus the executive KPIs (occupancy, condition index, satisfaction, overdue work-order rate, UH/MFH supply ratios) — recomputed client-side from the **filtered** installation set by the pure `housingFilters.aggregateInstallations()` using the read model's aggregate-input fields and identical weighting semantics (unfiltered values exactly match `/housing/overview`, unit-test pinned; metrics with no reporters in the subset show "n/a"). A status/branch/command filter strip (`HousingFilterStrip` + the pure `housingFilters.ts` module) narrows the band aggregates, map, ranking table, and status counts together. The installation detail card explains itself: a "Why this status" list rendered straight from the API's `status_reasons`, a reporters-only rank pill (backend `open_work_orders_rank` preferred, client fallback), and links into the scorecard run viewer at `/scorecards/:runId?kb=<kbId>` (`ScorecardRunPage`) — graded sections, metric health/completeness chips, citations, and JSON/Markdown export against the real export endpoint; these run links are the dashboard's only scorecard entry point. Scorecard generation has **no UI surface** (the earlier readiness panel and "Generate scorecard" button were retired 2026-07-07 in favor of the unified band): runs are created via `POST /scorecards/runs` by the seed tool and covered by backend router tests. With no housing rows ingested the page falls back to the public installation reference layer (`src/data/airForceInstallations.ts`) with placeholder band cards — no fabricated numbers.

**Seed path.** `make seed-housing` (→ `tools/seed_housing_demo.py`) drives the *running* API over real HTTP: creates a fresh KB, uploads the six housing feed fixture CSVs through `POST /records/{kb}/files`, waits for the ingest workflows, and optionally generates scorecard runs (`SEED_ARGS="--scorecards"`). Requires the stack running with the housing pack (`make dev-domain DOMAIN=department_air_force_housing`). Reseeding uses a fresh KB each run — the housing read models aggregate the newest KB of the active domain.

**Provenance.** Every UH (8-metric) and MFH (12-metric) template metric traces to a congressional mandate; the statutory basis, per-metric citations, and the honest simplifications the demo makes are documented in the research dossier at [`docs/research/housing-scorecard-mandates.md`](research/housing-scorecard-mandates.md).

### 6.9 Dead-letter queue: durable records + operator replay (BL-023)

`run_handler_with_retry` (`agent/coordinator.py`) publishes exhausted pipeline
handler failures to a capped, per-event-type Redis Streams `{stream}.dlq`
archive (`EventBus.publish_to_dlq`) — transport, not an operational record.
BL-023 adds a durable, queryable, replayable layer on top of that transport:

- **`event_dlq` table** (Alembic migration `0010_event_dlq`) or an in-memory
  adapter for tests/no-database dev, behind the `events.protocols.DlqRecordStore`
  protocol (`InMemoryDlqRecordStore` / `PostgresDlqRecordStore`,
  `backend/events/adapters/`). Selection mirrors the BL-041 document-status
  store: Postgres when a database connection provider is configured, else
  in-memory (`build_dlq_record_store` in the worker, `get_dlq_record_store` in
  the API gateway — both must select the **same** Postgres backend for the
  API to see worker-written records, or the in-memory case degenerates to two
  independent, process-local ledgers).
- **Writer**: after a successful `publish_to_dlq`, the worker best-effort
  persists a `DlqRecord` (event type, correlation id, codec-encoded payload,
  error message/traceback, retry count, timestamps). A persistence failure is
  logged and swallowed — it never masks the original handler failure, since
  the Redis archive entry from the step above already exists as a fallback.
  `persist` is an upsert keyed on `dlq_id` with a terminal-state guard: once a
  record is `replayed` or `discarded`, a later `persist` for that id is a
  no-op rather than reverting it to `pending`.
- **Operator API** (`GET/POST /events/dlq*` on the existing `/events` router):
  list (paginated, filterable by `status`/`event_type`) and inspect
  (`analyst`-gated — tracebacks can leak internals); replay and discard
  (`admin`-gated — they mutate pipeline state). Replay decodes the stored
  payload and re-publishes it through the normal `EventBus.publish` path, so
  it re-enters ordinary dispatch — per-document isolation (BL-041/BL-017) and
  status-projection idempotency apply exactly as they would to a fresh
  delivery, and a still-broken cause dead-letters again as a **new** record
  rather than looping the original.
- **Concurrency tradeoff (accepted by design)**: replay publishes the event
  before it CAS-transitions the record to `replayed`, so a race between two
  operator actions on the same record can publish the event once while only
  one call wins the transition (the other gets `409`) — never zero times.
  The alternative ordering (CAS first) risks the opposite: a record marked
  `replayed` with no event ever published if the process fails between the
  two steps. Accepted because downstream handlers are idempotent by
  construction (BL-041 monotonic projections, BL-017 replay-stable upserts),
  so a harmless extra publish is strictly safer than a silent loss.
- **Redaction is deliberately out of scope for v1** — no existing
  repo-wide redaction convention exists to follow, and event payloads are
  reference-shaped by construction (ids, storage keys, counts — never
  document content or credentials).

Full operator playbook (triage, replay/discard decision, curl examples, the
`event_dlq`-vs-`.dlq`-stream relationship): [`docs/runbooks/event-replay.md`](runbooks/event-replay.md).
Module design: [`backend/events/README.md`](../backend/events/README.md).

---

## 7. Knowledge Base Management

Knowledge bases are the core organizational unit for ingested content and their associated graphs and embeddings.

### 7.1 Operations

| Operation | Trigger | Pipeline steps | Notes |
|-----------|---------|----------------|-------|
| **Create KB** | `POST /knowledgebases` | Create metadata → publish `kb.create` | Returns `201 Created`; graph/vector namespace initialization is async/planned |
| **Add documents** | `POST /knowledgebases/{id}/documents` | Upload to object store → parse → chunk → extract entities → upsert graph → embed → index | Incremental — merges with existing graph |
| **View KB summary** | `GET /knowledgebases/{id}` | Read persisted metadata → merge live graph/object-store signals → persist projected status/counts | Returns document count, entity/relationship counts, and indexing status from the live KB projection |
| **List documents** | `GET /knowledgebases/{id}/documents` | Read persisted document metadata → derive status from KB projection | Paginated list with persisted/derived ingestion status per document |
| **Remove document** | `DELETE /knowledgebases/{id}/documents/{doc_id}` | Delete document metadata, object-store payloads, and the document's row (if any) in the durable status projection (`SourceDocumentStatusStore.delete_by_document`) | Graph/vector cascade cleanup via `delete_by_source_document` is called on the re-upload (changed-content) path; it is not yet wired to the document-delete endpoint |
| **Delete KB** | `DELETE /knowledgebases/{id}` | Cascade-purge every per-KB store (graph, vector, raw_records+submissions, derived signals, timeseries anomalies, risk history, observations, alert history (durable alert feed, alerts.36 — no separate API-owned projection step), GNN cluster summaries, metrics, conversations, cases, policy, evidence, scorecard runs, document-status projection, object store) → delete KB metadata → publish `kb.delete`. Shared step list: `knowledgebases.cleanup.kb_deletion_steps` (API + worker retry replay the same cascade) | Full 207 cascade implemented; workflow-busy 409 guard prevents deletion during active pipeline run |
| **Rebuild RAG index** | Planned | Re-embed all content → replace vector index | No current public route |

### 7.2 Metadata projection and lifecycle boundaries

The API owns the lightweight KB/document metadata projection through the `KnowledgeBaseRepository` protocol. Current repository adapters are:

- `in_memory` — isolated process-local metadata for unit tests and simple local runs.
- `object_store` — dev-stack durability that serializes KB/document metadata through the configured `ObjectStore` so API reloads do not lose inventory state. This is intentionally a single-writer development adapter, not a high-concurrency production metadata database.

Graph entities, relationships, and metrics remain owned by the `graph` module. KB list/detail/document reads call projection helpers that merge persisted KB metadata with live graph metrics and graph-build artifacts, then write changed status/count fields back through the repository. SSE workspace snapshots use the same projection path for `knowledge_base_statuses`, avoiding seeded demo state for live KB status.

Deleting a KB executes a full cascade across every per-KB durable store — graph, vector, `raw_records` + `record_submissions`, peerstats `entity_derived_signals`, timeseries anomalies (required in both bundles — analytics-owned, not API-owned, positioned directly after `derived_signals`), `risk_score_history`, `observations`, `alert_history` (a single step purges the durable alert feed too, since **alerts.36** retired the separate API-owned `alert_projection` step — `/alerts` now reads `alert_history` directly), GNN cluster summaries (required in both bundles — analytics-owned, not API-owned), `entity_metric_history`/`entity_metrics_current`, `conversations`, `cases`, `policy_items`, evidence packs, scorecard runs, the document-status projection, and object-store payloads — then KB repository metadata. The ordered step list lives in `knowledgebases.cleanup.kb_deletion_steps` (shared by the API endpoint and the worker's retry handler, so the two cannot drift); adding a new per-KB store is one field on `KbDeletionStores` + one step. A workflow-busy 409 guard prevents deletion while an active pipeline run is in progress. Document-level (single-document) cleanup purges graph/vector provenance via `delete_by_source_document(kb_id, doc_id)` and the status-projection row via `SourceDocumentStatusStore.delete_by_document(kb_id, doc_id)`.

### 7.3 Provenance tracking

Each entity and relationship in the graph carries provenance metadata linking it back to the source document(s) and extraction step. This enables:

- Cascading deletes when a document is removed (`delete_by_source_document` on graph and vector store)
- Audit trail for explainability (which document contributed which evidence)
- Incremental re-ingestion without full rebuild

Provenance fields: `source_kind` (`"document"` or `"record"`), `source_document_id` (SHA-256 of content), `source_chunk_id`, `source_feed` (records only), `source_raw_record_id` (records only). See §6.5 for the full field table and cascade delete sequence.

---


### 7.4 Dual-Graph Reads

The platform supports a dual-graph model: a domain-level reference ("policy") KB containing slow-changing reference data (codesets, exclusion lists, policy documents, provider directory) plus per-cycle transactional ("claims") KBs. Reads on the graph, vector store, and RAG layers span both via `knowledge_base_ids: list[str]` on the protocol surface. The API handler boundary resolves the primary KB into the full scope using `shared.kb_scope.resolve_kb_scope`, which honors the domain's optional `default_reference_kb_id`. Writes remain single-KB; the neighborhood traversal in the graph adapter (`query_neighborhood`) is also single-KB because cross-graph edges are not stored. Cross-KB property joining (e.g., matching providers by NPI across graphs) is deferred to consumer layers (RAG context builder, UI presentation).

## 8. Frontend Architecture

### 8.1 Technology stack

| Concern | Technology | Notes |
|---------|-----------|-------|
| Framework | React 19 | Functional components, hooks |
| Language | TypeScript 5.9.x (strict mode) | `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`; pinned to TS 5 while OpenAPI tooling requires `^5.x` |
| Build | Vite 8 | Dev server with HMR, production build |
| Routing | React Router v8 | File-system or config-based routes |
| Server state | TanStack Query (React Query) | Caching, invalidation, optimistic updates |
| Client state | Zustand | Lightweight store for UI state (selected entity, panel visibility, etc.) |
| API client | Typed fetch wrapper + TanStack Query hooks + generated OpenAPI schema aliases | `lib/apiClient.ts` handles transport; `src/api/contracts.ts` aliases `src/lib/api/schema.ts` generated from backend OpenAPI |
| Real-time | Server-Sent Events + WebSocket support | Workspace snapshots over SSE; WebSocket support remains available for push-style interactions |
| Graph visualization | `react-force-graph-2d` | Canvas graph explorer in the Investigation Workbench |
| Styling | CSS Modules + global app CSS | Component-scoped styles for complex UI surfaces |

> **Current state**: `chili_app/` is a routed React 19 workbench prototype with Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, Case Management, Policy Intelligence, RAG Chat, and a Configuration page hosting the Config Manager (pack switcher, dry-run validation, hot-swap apply; raw pack save remains a gap). Knowledge Base Manager uses the live KB repository, Investigation Workbench uses KB-scoped live `/investigation/*` graph APIs, and dashboard/alert/case/policy surfaces are backed by live service/repository projections. Remaining frontend gaps are configuration-write workflows, standalone workflow/evidence navigation surfaces, and production UX/performance hardening.

### 8.2 Page / view structure

```
chili_app/src/
├── main.tsx                    # App entry point
├── App.tsx                     # Root layout, routing
├── app/
│   └── providers.tsx           # QueryClient + providers
├── lib/
│   └── apiClient.ts            # Typed fetch wrapper
├── api/                        # Per-resource TanStack Query modules
│   ├── contracts.ts            # Aliases generated OpenAPI types
│   ├── config.ts               # Domain config queries (useDomainConfig)
│   └── …                       # alerts.ts, cases.ts, rag.ts, records.ts, …
├── stores/                     # Zustand stores
│   ├── appStore.ts             # Sidebar, selected entity, active KB
│   ├── chatStore.ts            # Local chat/session state
│   ├── uiStore.ts              # Panel/sidebar visibility, realtime status, role
│   └── ingestionStudioStore.ts # Ingestion Studio wizard state
├── pages/
│   ├── DashboardPage.tsx
│   ├── KnowledgeBaseManagerPage.tsx
│   ├── AlertFeedPage.tsx
│   ├── InvestigationWorkbenchPage.tsx
│   ├── CaseManagementPage.tsx
│   ├── PolicyIntelligencePage.tsx
│   ├── ScorecardRunPage.tsx
│   ├── HousingExecutivePage.tsx # /housing — map-led DAF housing dashboard (see §6.8)
│   ├── RagChatPage.tsx
│   ├── ConfigurationPage.tsx
│   └── Login.tsx
├── components/
│   ├── investigation/          # Graph explorer, entity detail, evidence, timeline
│   ├── alerts/                 # Alert list item, badge, detail
│   ├── chat/                   # RAG chat message list, input
│   ├── knowledgebase/          # KB tables, detail view, upload widgets
│   ├── housing/                # InstallationHealthMap (d3-geo Albers CONUS), summary band, filters, ranking
│   └── common/                 # Shared UI primitives (layout, loading, error)
└── hooks/                      # Shared custom hooks
    ├── useWebSocket.ts
    ├── useKnowledgeBases.ts
    └── useNeighborhood.ts
```

### 8.3 Investigation Workbench

The investigation workbench is the primary analyst view. It is a composite page with multiple coordinated panels. In the current prototype, the workbench selects an active knowledge base, searches entities through `/investigation/search?kb_id=...`, and loads entity detail plus neighborhood data through KB-scoped investigation endpoints. Entity titles, subtitles, chips, and relationship labels derive from the active domain config's entity/relationship definitions and `ui.display_fields` metadata instead of hardcoded Medicare-specific labels.

```
┌─────────────────────────────────────────────────────────────────┐
│  Investigation Workbench                              [config]  │
├───────────────────────────────────┬─────────────────────────────┤
│                                   │                             │
│                                   │  Entity Detail              │
│     Graph Explorer                │  ─────────────              │
│     (interactive force-directed   │  Name: Dr. Smith            │
│      or hierarchical graph)       │  Type: Provider             │
│                                   │  Risk Score: 0.87           │
│     • Click node → detail panel   │  Claims: 1,247              │
│     • Drag to explore             │  Cluster: #14               │
│     • Filter by entity type       │                             │
│     • Highlight risk scores       │  Relationships:             │
│                                   │  • 847 beneficiaries        │
│                                   │  • 12 facilities            │
│                                   │  • 3 flagged peers          │
├───────────────────────────────────┼─────────────────────────────┤
│                                   │                             │
│  Timeline                         │  Evidence Pack              │
│  ──────────                       │  ─────────────              │
│  ▁▂▃▅▇▅▃▂▁▂▃▅▇█▇▅▃▁ claims/mo  │  Reasoning:                 │
│  ─────────────────── anomaly      │  "Billing volume 3.2σ above │
│  Jan  Mar  May  Jul  Sep  Nov    │   peer mean. 4 beneficiaries│
│                                   │   shared with flagged       │
│                                   │   provider P-4421."         │
│                                   │                             │
│                                   │  Subgraph: [view]           │
│                                   │  Confidence: 0.91           │
└───────────────────────────────────┴─────────────────────────────┘
```

### 8.4 API communication

- The FastAPI OpenAPI document is the source of truth for frontend HTTP contracts. The frontend commits a generated schema at `chili_app/src/lib/api/schema.ts`; `chili_app/src/api/contracts.ts` only aliases generated schemas and may not define hand-written wire DTOs.
- Domain configuration remains runtime data: generated types describe the config structure, while entity names, relationship names, property names, record fields, and capabilities are read from `/config/domain`.
- The current frontend uses typed fetch helpers plus TanStack Query hooks over those generated contract aliases.
- TanStack Query wraps all API calls, providing caching, background refetching, and optimistic updates.
- The realtime workspace stream uses `GET /events/stream` as Server-Sent Events. Snapshots include live active-alert counts from the durable alert feed store (`AlertFeedStoreProtocol` over `alert_history`), live running-workflow counts from `AgentServiceProtocol`, and live KB statuses from the repository-backed KB projection. In the dev stack, API and worker share workflow lifecycle state through Redis.
- WebSocket support remains available for push-style interactions and follows typed message envelopes where applicable.

### 8.5 Domain-driven dynamic UI

The frontend reads the domain configuration from `GET /config/domain` at startup. This configuration drives:

- Entity type labels and icons in the graph explorer
- Relationship type labels on edges
- Which analytics panels are visible (e.g., hide time-series panel if `capabilities.timeseries` is disabled)
- Alert severity labels and thresholds displayed in the alert feed
- RAG chat system prompt context (domain-specific phrasing)

This means the same frontend codebase renders appropriately for Medicare fraud, food supply chain, or any other configured domain.

---

## 9. Domain Configuration Model

### 9.1 Configuration schema

The domain configuration is a single YAML (or JSON) file that defines all domain-specific behavior. A minimal example for the Medicare fraud exemplar:

```yaml
domain:
  name: medicare_fraud
  display_name: "Medicare Fraud Detection"
  description: "Fraud detection and investigator support for Medicare claims"

entities:
  - name: provider
    display_label: "Provider"
    icon: stethoscope
    properties:
      npi: { type: string, display: "NPI" }
      specialty: { type: string, display: "Specialty" }
      state: { type: string, display: "State" }

  - name: beneficiary
    display_label: "Beneficiary"
    icon: person
    properties:
      hic_number: { type: string, display: "HIC Number" }
      age: { type: integer, display: "Age" }
      chronic_conditions: { type: list, display: "Chronic Conditions" }

  - name: claim
    display_label: "Claim"
    icon: document
    properties:
      claim_id: { type: string, display: "Claim ID" }
      amount: { type: decimal, display: "Billed Amount" }
      service_date: { type: date, display: "Date of Service" }
      procedure_codes: { type: list, display: "Procedure Codes" }

  - name: facility
    display_label: "Facility"
    icon: building
    properties:
      facility_id: { type: string, display: "Facility ID" }
      name: { type: string, display: "Name" }
      type: { type: string, display: "Facility Type" }

relationships:
  - name: submitted_by
    display_label: "Submitted By"
    source: claim
    target: provider

  - name: billed_for
    display_label: "Billed For"
    source: claim
    target: beneficiary

  - name: performed_at
    display_label: "Performed At"
    source: claim
    target: facility

  - name: referred_by
    display_label: "Referred By"
    source: provider
    target: provider

capabilities:
  timeseries: true
  gnn: true
  risk_scoring: true
  rag_chat: true
  explainability: true
  structured_ingestion: true   # enables records/ pipeline and Plan C write-back flows

ingestion:
  sources:
    - type: file_upload
      formats: [pdf, docx, txt, csv, json, xlsx]
    - type: api_push
      format: json
      endpoint: /ingest/claims
  chunking:
    strategy: recursive          # recursive | fixed_size | sentence
    chunk_size: 1000
    chunk_overlap: 200
    min_chunk_size: 50

records:                         # structured-record ingestion (records/)
  feeds:
    - name: claims
      source: api_push
      entity_type: claim

graph_db:
  backend: in_memory             # in_memory | neo4j
vector_store:
  backend: in_memory             # in_memory | qdrant
  dimensions: 384
llm:
  provider: local                # local | openai | anthropic
  model: local-default
  api_key_env_var: OPENAI_API_KEY
embeddings:
  provider: local                # local | openai | sentence_transformers
object_store:
  backend: local                 # local | s3 (also serves MinIO)
event_bus:
  backend: in_memory             # in_memory | redis_streams

database:                        # Postgres + TimescaleDB (database/)
  backend: postgres              # in_memory | postgres
  dsn_env_var: CHILI_DATABASE_DSN
  pool_size: 10

monitoring:
  backend: in_memory             # in_memory | postgres (persists alerts + observations)

analytics:
  metrics_recompute_min_interval_seconds: 300  # MetricsRecomputeThrottle default
  timeseries:
    backend: in_memory           # in_memory | postgres
  risk:
    backend: in_memory           # in_memory | postgres (writer-only history)
  metrics:
    backend: in_memory           # in_memory | postgres
  narrative_backend: deterministic  # deterministic | llm (degrades to deterministic, never raises)
  attribution_backend: none         # none | shap (degrades to [], never raises)

gnn:
  snapshot_max_nodes: 5000       # cap on entities loaded per KB snapshot (top-degree kept)

rag:
  top_k: 8
  graph_expansion_hops: 1

auth:
  enabled: false                 # when false, requests run as anonymous viewer
  jwt_signing_key_env_var: JWT_SIGNING_KEY
  session_cookie_name: chiliai_session

alerts:
  thresholds:
    provider:
      risk_score: 0.75
      anomaly_sigma: 2.5
    beneficiary:
      risk_score: 0.80
    claim:
      amount_percentile: 99

ui:
  navigation:
    pages:
      - id: dashboard
        label: Dashboard
      - id: knowledge_bases
        label: Knowledge Bases
      - id: alerts
        label: Alert Feed
      - id: investigation
        label: Investigation
      - id: chat
        label: RAG Chat
      - id: configuration
        label: Configuration
  display_fields:
    provider: [npi, specialty, state]
    beneficiary: [hic_number, age]
    claim: [claim_id, amount, service_date]
  roles:
    - name: viewer
      can: [read]
    - name: analyst
      can: [read, ack_alert, chat]
    - name: admin
      can: [read, ack_alert, chat, manage_kb, manage_config]
```

> The full schema lives in [backend/config/schema.py](../backend/config/schema.py). The example above is illustrative; all blocks have sensible defaults so a minimal config only needs `domain`, `entities`, `relationships`, and `ingestion`.

### 9.2 How configuration flows through the system

```
                    ┌──────────────────┐
                    │  domain config   │
                    │  (YAML / JSON)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  config/loader   │
                    │  (validates,     │
                    │   parses into    │
                    │   typed objects) │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │  Backend   │  │  Backend   │  │  Frontend  │
     │  modules   │  │  API       │  │  (via GET  │
     │  (use at   │  │  (serves   │  │   /config/ │
     │  init)     │  │  to UI)    │  │   domain)  │
     └────────────┘  └────────────┘  └────────────┘
```

- **Backend modules** receive the parsed config at initialization (via dependency injection). The config determines which entity types to extract, which analytics modules to activate, and what alert thresholds to apply.
- **API** exposes `GET /config/domain` so the frontend can read the active configuration, plus admin-gated pack management: `GET /config/packs` (discover packs in the allow-listed config directories + active-pack state) and `POST /config/validate|apply|switch` (dry-run validation — optionally with env overlays applied via `?with_overlays=true`, see §9.2 — re-apply the active pack, or hot-swap to another pack).
- **Frontend** reads config at startup and caches it. All entity labels, icons, available panels, and feature gates are driven by this config. The Configuration page hosts the Config Manager (pack switcher + active-pack YAML editor with inline dry-run validation).

**Which file is active** is resolved by `config.store.resolve_config_path()` with strict precedence:

1. **Active-pack pointer** — `data/config/active_pack.json`, a small JSON state file written atomically (temp file + `os.replace`) by `POST /config/apply|switch`. Both the API and worker containers mount the same `chili-object-data` volume at `/app/data`, so the pointer is the shared channel through which a hot-swap survives restarts and propagates between containers. It deliberately bypasses the config-derived `ObjectStore` (that would be circular — the object-store backend comes from the config being resolved). Relocatable via `CHILI_ACTIVE_PACK_STATE_PATH`; `clear_active_pack()` deletes it.
2. **`CHILI_CONFIG_PATH`** environment variable — used only when no pointer exists.
3. Error — no silent default.

Consequence: once a pack has been switched via the UI/API, the persisted pointer **overrides** `CHILI_CONFIG_PATH` on every subsequent boot until it is cleared (switch back, or delete the state file).

**Base + environment overlays.** After the base file resolves via the precedence above and is parsed, `config.loader.load_config` reads `CHILI_CONFIG_OVERLAY_PATH` (comma-separated, declared order, last wins) and layers each overlay onto the base via `config.overlay.apply_overlays` — **before** `DomainConfig` validation runs. Overlay application happens on every load path (explicit `path`, plain `CHILI_CONFIG_PATH`, and the pointer-following `load_active_config`, which delegates to `load_config`), so it composes with pack hot-swap rather than bypassing it. Merge semantics: mappings deep-merge with overlay keys winning recursively; lists and scalars replace wholesale; an explicit `null` sets a field to `None`; there are no key-removal semantics. Every overlay file must declare `overlay_for: <pack filename stem>` — a mismatch against the resolved base pack's filename stem (`apply_overlays(..., base_path=...)`) **skips the overlay with a warning** instead of failing the boot, which is what lets `CHILI_CONFIG_OVERLAY_PATH` survive a runtime hot-swap to an unrelated pack; a missing `overlay_for` or an unknown top-level key is a hard `ConfigLoadError`. The guard is pack-scoped, not `domain.name`-scoped (2026-07-15 ADR 0001 amendment): packs sharing a `domain.name` (e.g. `medicare_fraud.yaml` and `medicare_fraud_cms_desynpuf.yaml`) no longer share an overlay. Overlays live in `backend/config/overlays/`, a directory the pack catalog (`api/routers/config.py`) does not iterate, so an overlay never appears as a switchable pack. `POST /config/validate` defaults to a raw pack/content dry run with **no** overlay layering (its verdict can then differ from what `apply` ultimately serves); passing `?with_overlays=true` dry-runs the merged result instead, via the same `apply_overlays(..., base_path=<resolved pack file>)` call `apply` uses — only valid for a pack reference (inline `content` has no base path to scope the guard, so that combination is a `422`), and a resulting `OverlayError` comes back as `valid=false, error_type="overlay_error"` rather than raising. Full rationale, the list-replace trade-off, and the associativity boundary (type-stable layer stacks only — see the amendment below): [ADR 0001](architecture/decisions/0001-config-overlay-merge-semantics.md).

Combined precedence, spanning both mechanisms: **path resolution** is explicit `path` argument > active-pack pointer > `CHILI_CONFIG_PATH` env var (as above); **overlay layering** then applies on top of whichever base won, in declared order — **base ← overlay₁ ← overlay₂ …** (last wins).

### 9.3 Active-pack hot-swap (no-restart domain switch)

`POST /config/apply` (re-apply the on-disk active pack, e.g. after editing it) and `POST /config/switch` (activate a different pack) execute a **swap-once-success** pipeline — a failure at any step leaves the previous domain fully active:

1. **Validate + guardrail.** The candidate pack is loaded through the full `DomainConfig` validator, then `api.dependencies.enforce_production_guardrail` is applied to its `auth` section — under `CHILI_ENV=staging|production` a pack that disables auth (or ships an incomplete OIDC config) is rejected *before* anything mutates. The same guardrail runs at boot in `create_app()`, so neither boot path nor swap path can silently drop auth.
2. **Persist pointer.** The active-pack pointer is written atomically (see §9.2).
3. **Atomic DI swap.** `reset_domain_config_caches()` clears `get_domain_config` and every config-keyed factory cache and bumps a monotonic **swap generation** token (`get_config_generation`). Factories are generation-guarded: a build started under an old generation refuses to publish into the new one, so a concurrent request observes a wholly-old or wholly-new dependency graph — never a torn mix.
4. **Emit `config.updated`.** A typed `ConfigUpdatedEvent` is published on the **pre-swap** event transport (captured before the caches reset) so the worker learns about the swap on the bus it is actually listening to.

**Worker convergence:** the worker (`agent/coordinator.py`) consumes `config.updated` between drain iterations — a rebuild never interleaves with in-flight event handling — and rebuilds its `WorkerDependencies` from the pointer-resolved config. Redelivery is idempotent (`ConfigReloadState` tracks the last applied delivery).

**Constraint — event transport is swap-invariant:** because the reload signal travels on the pre-swap transport and the worker keeps consuming the stream it subscribed to, a pack must **not** change the `events` backend/URI across a hot-swap. Changing the event transport (e.g. redis → in_memory) requires a restart. The shipped packs all pin the same dev-stack transport (`redis://redis:6379`).

Admin RBAC gates the whole surface (`require_role("admin")`), and pack references are confined to allow-listed config directories — no arbitrary filesystem reads. There is intentionally no raw pack read/write endpoint yet: the Config Manager validates edited YAML inline (dry-run with content), but "Apply" re-applies the on-disk file (future config-write work is charted in `docs/backlog/config.md` config.07/config.14).

### 9.4 Reconfiguring for a new domain

To retarget chiliAI from Medicare fraud to food supply chain monitoring:

1. Write a new domain config YAML defining entities and relationships — or use the shipped exemplar-parity pack `backend/config/defaults/food_supply_chain.yaml` (8 entities such as `supplier`, `facility`, `product_lot`, `shipment`; 11 relationships such as `shipped_by`, `inspected_at`; 4 records feeds; 3 policy rule packs; full `ui` section).
2. Select it: `make dev-domain DOMAIN=food_supply_chain` at stack start, **or** hot-swap a running stack from the Configuration page / `POST /config/switch` (no restart; the worker converges via `config.updated`).
3. The frontend picks up the new config on next load; knowledge bases are stamped with the domain that created them, and the UI badges KBs whose domain mismatches the active one.
4. Create a new knowledge base and ingest domain-relevant documents.

No application code changes required — only the configuration file. See `backend/config/README.md` for the pack-authoring contract and switch ergonomics (including the pointer-precedence gotcha).

---

## 10. Deployment Architecture

### 10.1 Container images

| Image | Base | Contents |
|-------|------|----------|
| `chili-app` | nginx:alpine | Built React SPA static assets. Serves via nginx with SPA fallback routing. |
| `chili-api` | python:3.12-slim | FastAPI application. Entry point: `uvicorn api.app:create_app`. |
| `chili-worker` | python:3.12-slim | Same codebase as API, different entry point. Runs pipeline consumer(s). |

### 10.2 Development environment

```yaml
# docker-compose.dev.yaml (representative)
services:
  app:
    build: ./chili_app
    ports: ["5173:5173"]        # Vite dev server
  api:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      # Domain pack selector — parameterized, medicare exemplar default.
      # Override via `make dev-domain DOMAIN=<pack>` or CHILI_CONFIG_PATH.
      - CHILI_CONFIG_PATH=${CHILI_CONFIG_PATH:-/app/config/defaults/medicare_fraud_cms_desynpuf.yaml}
      - CHILI_KB_REPOSITORY_BACKEND=object_store
      - CHILI_WORKFLOW_RUN_STORE_BACKEND=redis
      - REDIS_URL=redis://redis:6379
    depends_on: [redis]
  worker:
    build: ./backend
    command: python -m agent.coordinator  # or dedicated worker entry point
    environment:
      # Must match the api service — api and worker move domains together.
      - CHILI_CONFIG_PATH=${CHILI_CONFIG_PATH:-/app/config/defaults/medicare_fraud_cms_desynpuf.yaml}
      - CHILI_WORKFLOW_RUN_STORE_BACKEND=redis
      - REDIS_URL=redis://redis:6379
    depends_on: [redis]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  neo4j:
    image: neo4j:5
    ports: ["7474:7474", "7687:7687"]
```

### 10.3 Production deployment (Kubernetes)

```
┌──────────────────────────────────────────────────────────────┐
│  Kubernetes Cluster                                          │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ Ingress    │  │ chili-app  │  │ chili-api              │ │
│  │ Controller │─▶│ Deployment │  │ Deployment             │ │
│  │            │  │ (nginx)    │  │ (FastAPI, N replicas)  │ │
│  └────────────┘  └────────────┘  └───────────┬────────────┘ │
│                                              │              │
│                              ┌───────────────┤              │
│                              ▼               ▼              │
│                  ┌────────────────┐  ┌───────────────────┐  │
│                  │ Redis          │  │ chili-worker       │  │
│                  │ (StatefulSet   │  │ Deployment         │  │
│                  │  or managed)   │  │ (N replicas,       │  │
│                  └────────────────┘  │  consumer groups)  │  │
│                                      └───────────────────┘  │
│                                                              │
│  External (managed or self-hosted):                          │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Graph DB │  │ Vector Store │  │ Object Store │          │
│  └──────────┘  └──────────────┘  └──────────────┘          │
└──────────────────────────────────────────────────────────────┘
```

### 10.4 Scaling strategy

| Component | Scaling mechanism | Notes |
|-----------|-------------------|-------|
| **chili-app** | Horizontal (nginx instances behind CDN/LB) | Stateless; effectively infinite scale |
| **chili-api** | Horizontal (FastAPI behind load balancer) | Stateless; scale based on request volume |
| **chili-worker** | Horizontal (Redis consumer groups) | Each replica joins a consumer group; Redis distributes events. Scale based on pipeline throughput needs. |
| **Redis** | Vertical or Redis Cluster | Streams throughput is typically sufficient with a single node; cluster for HA |
| **Graph DB** | Per vendor scaling docs | Current external backend: Neo4j read replicas. |
| **Vector Store** | Per vendor scaling docs | Current external backend: Qdrant sharding. |

### 10.5 Hybrid deployment

The same container images deploy identically to:

- **Cloud**: AWS EKS, GCP GKE, Azure AKS — with managed Redis (ElastiCache), managed graph DB (Neptune), managed vector store, and S3 object storage.
- **On-premises**: Docker Compose or self-managed Kubernetes — with self-hosted Redis, Neo4j, Qdrant, and MinIO or local filesystem.

Adapter selection is driven by environment configuration, not code changes.

---

## 11. Observability

### 11.1 Logging

- **Library**: `structlog` (Python backend)
- **Format**: Structured JSON logs in production; human-readable in development
- **Correlation**: Each request and pipeline event carries a `trace_id` and `span_id` for end-to-end tracing
- **Levels**: DEBUG (dev only), INFO (request lifecycle, pipeline steps), WARNING (degraded performance, retries), ERROR (failures)

### 11.2 Metrics

- **Library**: Prometheus client (`prometheus-client` Python package)
- **Key metrics**:
  - `http_requests_total` — API request count by method, path, status
  - `http_request_duration_seconds` — API latency histogram
  - `pipeline_events_processed_total` — Events consumed by workers, by event type
  - `pipeline_step_duration_seconds` — Duration of each pipeline step (ingestion, embedding, analysis)
  - `graph_query_duration_seconds` — Graph DB query latency
  - `alerts_generated_total` — Alerts created, by entity type and severity
  - `knowledgebase_documents_total` — Documents per KB
  - Implemented today (BL-043 and prior): `pipeline_stage_duration_seconds` / `pipeline_errors_total` (`monitoring/metrics.py`), `ingestion_documents_failed_total{stage,error_class}` / `ingestion_documents_empty_extraction_total` / `ingestion_dedup_suppressed_total{kind}` (`shared/metrics.py`, the contracts-library home for counters incremented from more than one module — precedent: `shared/logging.py`, `shared/tracing.py`)
- **Export**: `GET /metrics` on the API container (`api/middleware/metrics.py`) **and** `GET /metrics` on the worker's health server (`agent/health.py`, port `8001` by default). These are separate `prometheus_client` registries in separate processes — a worker-side increment is invisible on the API's endpoint and vice versa, so a scrape config must target both.

### 11.3 Distributed tracing

- **Library**: OpenTelemetry SDK (installed via the optional `[observability]` extra in `backend/pyproject.toml`; falls back to no-op spans when the extra is absent)
- **Propagation**: W3C Trace Context across HTTP calls and Redis Stream events (trace ID embedded in event metadata)
- **Export**: OTLP to Jaeger, Tempo, or cloud-native tracing backend

### 11.4 Frontend observability

- **Error tracking**: Sentry (or equivalent) for unhandled exceptions and performance monitoring
- **Analytics**: Optional — may add product analytics for usage patterns in the investigation workbench

---

## 12. Security

> **Current state**: Authentication and authorization middleware, `/auth/*` routes, cookie/Bearer token handling, frontend login/session flow, route-level `require_role`, auth-enabled default-deny startup audit, kid-aware JWKS rotation, and OIDC nonce validation are implemented (BL-022, 2026-07-15). Remaining hardening focuses on tenant isolation, resource-level authorization, and live-IdP verification of the desk-checked Keycloak/Okta templates.

### 12.1 Authentication

- **Approach**: Pluggable FastAPI middleware
- **Protocols**: JWT verification with support for OIDC/OAuth2 identity providers
- **Configuration**: Auth enabled/disabled via domain config. When disabled, requests run as an anonymous `viewer`. When enabled, protected routes accept the `chiliai_session` cookie or a Bearer token.
- **Token flow**: The frontend uses a BFF-style cookie session; Bearer tokens remain supported for API clients.
- **Token validation (BL-022)**: `decode_token` (`backend/api/middleware/auth.py`) validates RS256 signature, `iss`, `aud`, and `exp` against the JWKS at `AuthConfig.jwks_uri`. `JwksCache` resolves the signing key by the token header's `kid`; an unknown `kid` triggers one forced JWKS refetch, throttled to at most once per URI per 30 seconds, so an IdP key rotation recovers automatically without a restart or waiting out the TTL. The OIDC login/callback flow additionally generates a `nonce` alongside the PKCE verifier and validates it against the decoded `id_token`'s `nonce` claim — id_token flows only (truthy `id_token` present); the access-token fallback path has no `nonce` claim to check. See [`docs/auth/idp-templates.md`](auth/idp-templates.md) for worked Keycloak/Okta configuration (desk-checked against IdP documentation, not verified against a live IdP).

### 12.2 Authorization

| Role | Permissions |
|------|------------|
| **admin** | Full access: configuration, KB management, user management, all analyst capabilities |
| **analyst** | View dashboards, investigate alerts, explore graph, use RAG chat, manage own alerts. Cannot modify system config or delete KBs. |
| **viewer** | Read/exploration access to dashboards, alert feed, graph/investigation views, and RAG chat. Mutations are reserved for analyst/admin roles. |

- **Enforcement**: Middleware + dependency injection at the API router level. Each router declares required roles.
- **Check granularity**: Route-level (not field-level). Finer-grained permissions can be added later.

### 12.3 Multi-tenancy (designed-for)

- **Isolation model**: Each tenant gets separate knowledge base namespaces, graph partitions, and vector store namespaces.
- **Tenant resolution**: From JWT claims (tenant ID). Injected into all downstream service calls.
- **Data separation**: Enforced at the adapter layer — graph queries, vector searches, and object store paths are always scoped to the active tenant.

### 12.4 Data protection

| Concern | Approach |
|---------|----------|
| **In transit** | TLS 1.3 for all HTTP, WebSocket, and database connections |
| **At rest** | Encrypted volumes for databases, object store, and Redis (if persisted). Delegated to infrastructure layer (EBS encryption, PV encryption). |
| **Secrets management** | Environment variables in dev; Kubernetes Secrets or external vault (HashiCorp Vault, AWS Secrets Manager) in production |
| **Input validation** | Pydantic models on all API inputs; file type and size validation on uploads |
| **Rate limiting** | API-level rate limiting middleware (deferred, add when exposed to untrusted clients) |

---

## 13. Technology Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend framework** | React 19 | UI components, state management |
| **Frontend language** | TypeScript 5.9.x (strict) | Type-safe frontend code; held on TS 5 for OpenAPI tooling compatibility |
| **Frontend build** | Vite 8 | Dev server, production bundling |
| **Frontend routing** | React Router v8 | Client-side navigation |
| **Server state (FE)** | TanStack Query | API data fetching, caching, invalidation |
| **Client state (FE)** | Zustand | Lightweight UI state |
| **Graph visualization** | `react-force-graph-2d` | Interactive graph explorer in the current prototype |
| **Backend language** | Python 3.12 | All backend services |
| **API framework** | FastAPI | HTTP + WebSocket gateway |
| **Type checking** | pyright (strict, scoped via `tool.pyright.include`) | Static type analysis |
| **Testing** | pytest + coverage | Unit/integration tests, ≥85% coverage |
| **Event streaming** | Redis 7+ Streams | Pipeline orchestration, decoupling |
| **Graph database** | in-memory / Neo4j | Knowledge graph storage (pluggable through the graph repository protocol) |
| **Vector store** | in-memory / Qdrant | Embedding storage, similarity search (pluggable through the vector store protocol) |
| **LLM integration** | local / OpenAI / Anthropic / Ollama (vLLM is roadmap-only) | RAG answers, entity extraction (pluggable) |
| **Embedding models** | OpenAI / sentence-transformers / custom | Text and graph-metric embeddings (pluggable) |
| **Object storage** | S3 / MinIO / local FS | Raw document persistence (pluggable) |
| **Logging** | structlog | Structured JSON logging |
| **Metrics** | Prometheus | Operational metrics |
| **Tracing** | OpenTelemetry | Distributed tracing |
| **Error tracking (FE)** | Sentry or equivalent | Frontend error monitoring (future production hardening) |
| **Containerization** | Docker | Image packaging |
| **Orchestration** | Kubernetes / Docker Compose | Production / dev deployment |
| **Infra-as-code** | Terraform or Pulumi | Cloud infrastructure (deferred, `infra/` directory exists) |

---

## 14. Open Questions & Future Work

### 14.1 Decisions to make during implementation

| Question | Context | Recommendation |
|----------|---------|----------------|
| **Agent framework** | The `agent/` module needs a coordination mechanism for multi-step pipelines. | Start with a custom async state machine with pluggable step handlers. Evaluate LangGraph adoption once pipeline complexity (branching, tool-use, human-in-the-loop) warrants a framework. |
| **Graph visualization library** | The current Investigation Workbench uses `react-force-graph-2d`. | Keep it for the prototype; evaluate WebGL alternatives or route-level code splitting if representative large graphs expose performance limits. |
| **Embedding model** | RAG quality depends heavily on embedding model choice. | Start with `sentence-transformers` (all-MiniLM-L6-v2 or similar) for fast iteration. Evaluate OpenAI embeddings for quality comparison. Consider domain-specific fine-tuning after the pipeline is functional. |
| **Batch scheduling** | Some analytics (GNN training, full re-embedding) are compute-heavy batch jobs. | Start with Redis-triggered workers. Evaluate Celery, Airflow, or a simple cron-based approach if scheduling complexity grows. |
| **Frontend styling** | CSS Modules plus global app CSS are in use. | Keep component CSS scoped; evaluate a component library only if repeated interaction patterns justify it. |

### 14.2 Future capabilities

| Capability | Description | Priority |
|------------|-------------|----------|
| **CI/CD pipeline** | Baseline lint, type-check, test, build, and dependency audits run in GitHub Actions. | Add deploy/promotion jobs once environments are finalized. |
| **Authentication & RBAC** | Pluggable auth middleware, role enforcement. See §12. Implemented 2026-05-08; JWKS kid-rotation + OIDC nonce validation + desk-checked Keycloak/Okta templates added 2026-07-15 (BL-022). Remaining hardening: tenant isolation, resource-level authorization, live-IdP verification of the templates. | Medium — tenant isolation before multi-user deployment |
| **Multi-tenancy** | Tenant-isolated data, config, and KB namespaces. | Medium — after auth |
| **Configuration UI wizard** | Sectioned, schema-driven configuration wizard. A first Config Manager page exists (pack switcher + raw YAML editor with dry-run validation and hot-swap apply, §9.3); typed per-section forms, drafts, and a config write path remain. | Medium |
| **Model training pipeline** | Scheduled/triggered GNN training, embedding fine-tuning. | Medium |
| **Audit log** | Track all analyst actions (graph queries, alert acks, config changes) for compliance. | Medium |
| **Export / reporting** | Generate PDF/CSV reports of investigations, evidence packs, risk summaries. | Low — after core workbench is functional |
| **Plugin system** | Allow third-party analytics modules to be added without modifying core. | Low — after architecture stabilizes |

### 14.3 Current state vs. target

> **Last updated**: May 2026. For implementation status, verify the current code and tests first. Historical status reports and retired planning docs live under [`docs/archive/`](archive/). Current production-readiness gaps are tracked in the module backlogs under [`docs/backlog/`](backlog/) and the curated PM backlog under [`docs/project/planning/`](project/planning/).

| Component | Current state | Next milestone |
|-----------|---------------|----------------|
| `backend/` | Active FastAPI/worker prototype with domain config, typed shared contracts, event bus, ingestion (LLM-driven `LlmDocumentExtractor` + Ollama adapter + `FallbackLlmClient`; registered PDF/DOCX/HTML/TXT/JSON/CSV/XLSX parsers), graph/vector/embedding/LLM/RAG services, analytics modules (timeseries/gnn/risk/explainability/metrics), monitoring, storage adapters, auth/RBAC middleware, route-level guards, live KB metadata projection, worker-updated workflow lifecycle tracking, SSE workspace snapshots, `database/` (psycopg 3 + Alembic + TimescaleDB) connection provider, `records/` structured-ingestion pipeline (raw_records + embed+index step + NPPES/DE-SynPUF feeds), KB delete cascade purging every per-KB store (graph/vector/raw_records+submissions/derived signals/risk history/observations/alert history/metrics/conversations/cases/policy/evidence/scorecard runs/document-status projection/object store; shared step list in `knowledgebases.cleanup`, replayed by both the API and the worker) with 207 partial-failure + complete worker retry, document re-upload idempotency with `replaced_document_id`, `delete_by_source_document` on graph and vector protocols, `delete_by_document` on the document-status store (called from the single-document delete endpoint), `delete_by_kb` on raw records, provenance metadata constants (`shared/provenance.py`), Tennessee subset tooling (`tools/sample_data/build_tennessee_subset.py`), Plan C per-consumer Postgres adapters with write-back flows in `agent/coordinator.py`, and a durable/replayable event dead-letter ledger with an `analyst`/`admin`-gated operator API surface (`event_dlq` table, `/events/dlq*`, BL-023 — see §6.9) | Add a production-grade KB metadata adapter/migration path, wire `delete_by_source_document` to the document-delete endpoint, add production-mode adapter guardrails, and add audit-grade workflow history |
| `chili_app/` | Routed React 19 analyst workbench prototype with Dashboard, Knowledge Base Manager/detail/upload UI, Alert Feed, live KB-scoped Investigation Workbench, Case Management, Policy Intelligence, RAG Chat, Configuration page with Config Manager (pack switch/apply; config save still a gap), and realtime SSE hook | Complete config save endpoint integration, add dedicated workflow/evidence navigation surfaces, and production UX/performance polish |
| `docs/` | Architecture, onboarding guide, security checklist, live module backlogs, curated project planning, superpowers plans/specs, wiki, ledger, and archived historical material | Keep active docs synchronized with implementation and archive stale snapshots |
| `infra/` | Docker Compose, flat Kubernetes manifests, and Helm chart | Add cloud-provider Terraform/Pulumi and production hardening as needed |
| Testing | Extensive backend pytest suite and frontend Vitest suite | Keep CI coverage gates calibrated and add live adapter profiles where services are available |
| CI/CD | GitHub Actions baseline exists | Add deployment/promotion workflows after release environments are defined |
