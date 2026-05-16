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

- **Backend**: Python 3.12. All code must be compatible with `pyright --strict` — full annotations, no untyped `Any`, explicit domain types.
- **Frontend**: TypeScript in strict mode (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`).

### 2.6 Test-driven quality

Backend test suites must maintain **≥ 85% coverage** for affected packages. Missing tests are treated as incomplete work. Tests are isolated and deterministic — external systems are mocked or faked at the adapter boundary.

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
| **Auth provider** | *(Future)* External identity provider (OIDC/OAuth2) for authentication. Designed-for but deferred. |

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
| **Postgres / TimescaleDB** | PostgreSQL + TimescaleDB extension | Persists structured records, time-series observations, entity metric history (hypertable), current entity metrics, risk score history, and alert history. Accessed exclusively through the `database` module's `ConnectionProvider` protocol and Alembic-managed schema. |

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

```
backend/
├── main.py                     # Local Uvicorn launcher
├── pyproject.toml              # Project metadata, dependencies
├── api/                        # FastAPI gateway layer
│   ├── __init__.py
│   ├── app.py                  # FastAPI application factory
│   ├── dependencies.py         # Dependency injection wiring
│   └── routers/
│       ├── knowledgebases.py   # KB CRUD, document management
│       ├── alerts.py           # Alert feed, acknowledgment
│       ├── investigation.py    # Graph queries, entity detail
│       ├── chat.py             # RAG chat endpoints
│       ├── analytics.py        # Analytics endpoints
│       ├── config.py           # Domain configuration endpoints
│       └── ws.py               # WebSocket hub for real-time push
├── ingestion/                  # Document parsing & entity extraction
│   ├── __init__.py
│   ├── parsers/                # Format-specific parsers (PDF, DOCX, HTML, JSON, TXT)
│   ├── chunker.py              # Text chunking strategies
│   ├── extractor.py            # Entity & relationship extraction (uses LLM adapter)
│   └── models.py               # Ingestion-internal data models
├── graph/                      # Graph database access
│   ├── __init__.py
│   ├── protocols.py            # Abstract GraphRepository protocol
│   ├── models.py               # Graph-layer data models
│   └── adapters/
│       ├── in_memory.py
│       └── neo4j_adapter.py
├── vectorstore/                # Vector store access
│   ├── __init__.py
│   ├── protocols.py            # Abstract VectorStore protocol
│   └── adapters/
│       ├── in_memory.py
│       └── qdrant_adapter.py
├── embeddings/                 # Embedding generation
│   ├── __init__.py
│   ├── protocols.py            # Abstract Embedder protocol
│   └── adapters/
│       ├── in_memory.py
│       ├── openai_adapter.py
│       └── sentence_transformers_adapter.py
├── rag/                        # Retrieval-augmented generation pipeline
│   ├── __init__.py
│   ├── service.py              # Query → embed → search → expand → assemble → LLM → answer
│   ├── service_models.py
│   └── adapters/               # Bridges to embeddings, vectorstore, graph, and LLM services
├── llm/                        # LLM client abstraction
│   ├── __init__.py
│   ├── protocols.py            # Abstract LLMClient protocol
│   ├── prompts.py              # Prompt templates and management
│   └── adapters/
│       ├── in_memory.py
│       ├── openai_adapter.py
│       └── anthropic_adapter.py
├── analytics/                  # ML / AI capability modules
│   ├── __init__.py
│   ├── timeseries/             # Time-series anomaly detection
│   │   ├── __init__.py
│   │   ├── detector.py
│   │   └── models.py
│   ├── gnn/                    # Graph neural network analysis
│   │   ├── __init__.py
│   │   ├── link_prediction.py
│   │   └── clustering.py
│   ├── risk/                   # Risk scoring engine
│   │   ├── __init__.py
│   │   └── scorer.py
│   └── explainability/         # Evidence pack generation
│       ├── __init__.py
│       ├── evidence.py         # Build evidence packs (reasoning, subgraph, scores)
│       └── subgraph.py         # Extract explanatory subgraph patterns
├── agent/                      # Workflow / pipeline coordinator
│   ├── __init__.py
│   ├── coordinator.py          # Async state machine for multi-step pipelines
│   ├── steps.py                # Pluggable step handlers
│   └── models.py               # Pipeline state, step result types
├── monitoring/                 # Active monitoring service
│   ├── __init__.py
│   ├── consumer.py             # Claim stream consumer
│   └── alerting.py             # Threshold evaluation, alert generation
├── shared/                     # Lightweight shared contracts library
│   ├── __init__.py
│   ├── types.py                # Generic platform types: Entity, Relationship,
│   │                           #   Alert, EvidencePack, KnowledgeBase
│   ├── protocols.py            # Cross-cutting protocol definitions
│   └── utils.py                # Small, dependency-light utilities
├── config/                     # Domain configuration
│   ├── __init__.py
│   ├── loader.py               # Reads YAML/JSON domain config
│   ├── schema.py               # Config schema definition & validation
│   └── defaults/               # Example domain configs
│       ├── medicare_fraud.yaml
│       └── food_supply_chain.yaml
├── events/                     # Event bus abstraction
│   ├── __init__.py
│   ├── protocols.py            # Abstract EventBus protocol
│   ├── types.py                # Event type definitions
│   └── adapters/
│       └── redis_streams.py    # Redis Streams implementation
├── storage/                    # Object / file storage abstraction
│   ├── __init__.py
│   ├── protocols.py            # Abstract ObjectStore protocol
│   └── adapters/
│       ├── s3.py
│       ├── minio.py
│       └── local.py
├── database/                   # Postgres + TimescaleDB connection provider, Alembic migrations
│   ├── __init__.py
│   ├── protocols.py            # ConnectionProvider, DatabaseConnection, DatabaseCursor
│   ├── engine.py               # psycopg 3 pool-backed provider (lazy import)
│   ├── runtime.py              # create_connection_provider(config) factory
│   ├── health.py               # check_database_health(provider) readiness probe
│   ├── exceptions.py           # Module-specific exceptions
│   └── migrations/             # Alembic environment + versioned raw-SQL migrations
└── records/                    # structured/tabular ingestion (CSV/JSONL/api-push), raw_records landing
    ├── __init__.py
    ├── models.py               # RawRecord, RecordBatch, content_hash_for (idempotency digest)
    ├── service_models.py       # RecordSubmission, RecordIngestReceipt (API boundary)
    ├── validation.py           # coerce_row / validate_rows (feed schema validation)
    ├── service.py              # RecordsService.register_records(): validate → persist → publish
    ├── protocols.py            # RecordsServiceProtocol (service boundary)
    ├── exceptions.py           # Module-specific exceptions
    ├── mappers/
    │   └── feed_mapper.py      # map_batch (rows → entities/relationships), map_observations
    └── adapters/
        ├── protocols.py        # RawRecordStore, RecordSourceProtocol
        ├── in_memory.py        # InMemoryRawRecordStore (local/test backend)
        ├── postgres.py         # PostgresRawRecordStore (raw_records table)
        └── sources/
            ├── file_source.py      # CsvFileSource, JsonlFileSource
            └── api_push_source.py  # ApiPushSource
```

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
| `agent` | Pipeline coordination, state machine | `events` (protocol), `shared.types` | Direct imports of service internals |
| `monitoring` | Stream consumption, alert generation | `shared.types`, `events` (protocol) | `api`, `ingestion` internals |
| `shared` | Domain types, protocols, utilities | Python stdlib only | Everything — must be leaf dependency |
| `config` | Configuration loading and validation | `shared.types` | Everything except `shared` |
| `events` | Event bus abstraction | `shared.types` | Everything except `shared` |
| `storage` | Object/file storage abstraction | `shared.types` | Everything except `shared` |
| `database` | Connection pooling, schema migrations | `config`, `shared` | domain logic, business logic, imports of any capability module |
| `records` | Structured-record validation, raw_records persistence, feed mapping | `config`, `shared`, `events`, `database`, `monitoring.models` | imports of `graph`/`analytics` internals — communicates downstream only by publishing `RecordsIngestedEvent` |

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
  └── map_observations() → PostgresObservationStore.write_observations()
                              # observations table (idempotent upsert)
```

Every write is an idempotent upsert keyed on `(knowledge_base_id, record_type, record_id)` for `raw_records` and on `(entity_id, metric_name, observed_at)` for `observations`, so the worker's retry/DLQ wrapper can re-run the handler safely without duplicating data.

`GraphService.upsert_records_graph` is the records-specific graph entry point. Unlike the document pipeline's `upsert_graph`, it accepts no document artifacts and does not publish a `GraphUpdatedEvent`. The `observations` table has a write-side adapter at `monitoring/adapters/postgres.py` (`PostgresObservationStore`).

### 6.4 Self-reinforcing analysis loop

The analytics pipeline is designed as a **feedback loop**: analysis results (risk scores, cluster memberships, anomaly flags) are written back to the knowledge graph, enriching it for subsequent analysis rounds. This means:

- GNN link prediction benefits from risk scores computed in previous rounds
- Time-series anomaly detection can incorporate graph-derived features
- Risk scoring aggregates signals from both time-series and GNN outputs
- Each monitoring cycle produces a progressively richer graph

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
| **Remove document** | `DELETE /knowledgebases/{id}/documents/{doc_id}` | Delete document metadata and object-store payloads | Graph/vector provenance-backed cleanup is planned |
| **Delete KB** | `DELETE /knowledgebases/{id}` | Delete object-store payloads → clear graph namespace through `GraphServiceProtocol` → delete KB metadata → publish `kb.delete` | Vector namespace teardown remains planned |
| **Rebuild RAG index** | Planned | Re-embed all content → replace vector index | No current public route |

### 7.2 Metadata projection and lifecycle boundaries

The API owns the lightweight KB/document metadata projection through the `KnowledgeBaseRepository` protocol. Current repository adapters are:

- `in_memory` — isolated process-local metadata for unit tests and simple local runs.
- `object_store` — dev-stack durability that serializes KB/document metadata through the configured `ObjectStore` so API reloads do not lose inventory state. This is intentionally a single-writer development adapter, not a high-concurrency production metadata database.

Graph entities, relationships, and metrics remain owned by the `graph` module. KB list/detail/document reads call projection helpers that merge persisted KB metadata with live graph metrics and graph-build artifacts, then write changed status/count fields back through the repository. SSE workspace snapshots use the same projection path for `knowledge_base_statuses`, avoiding seeded demo state for live KB status.

Deleting a KB removes its object-store payloads and invokes graph namespace cleanup through `GraphServiceProtocol.delete_knowledge_base()`. API code does not import concrete graph adapters; in-memory and Neo4j cleanup behavior is provided behind the graph repository protocol. Document-level graph/vector cleanup remains future work until provenance-backed delete semantics are implemented.

### 7.3 Provenance tracking

Each entity and relationship in the graph carries provenance metadata linking it back to the source document(s) and extraction step. This enables:

- Cascading deletes when a document is removed
- Audit trail for explainability (which document contributed which evidence)
- Incremental re-ingestion without full rebuild

---

## 8. Frontend Architecture

### 8.1 Technology stack

| Concern | Technology | Notes |
|---------|-----------|-------|
| Framework | React 19 | Functional components, hooks |
| Language | TypeScript 5.9.x (strict mode) | `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`; pinned to TS 5 while OpenAPI tooling requires `^5.x` |
| Build | Vite 8 | Dev server with HMR, production build |
| Routing | React Router v7 | File-system or config-based routes |
| Server state | TanStack Query (React Query) | Caching, invalidation, optimistic updates |
| Client state | Zustand | Lightweight store for UI state (selected entity, panel visibility, etc.) |
| API client | Typed fetch wrapper + TanStack Query hooks | `lib/apiClient.ts` provides typed envelopes; generated OpenAPI client remains optional future hardening |
| Real-time | Server-Sent Events + WebSocket support | Workspace snapshots over SSE; WebSocket support remains available for push-style interactions |
| Graph visualization | `react-force-graph-2d` | Canvas graph explorer in the Investigation Workbench |
| Styling | CSS Modules + global app CSS | Component-scoped styles for complex UI surfaces |

> **Current state**: `chili_app/` is a routed React 19 workbench prototype with Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, and Configuration views. Knowledge Base Manager uses the live KB repository, and Investigation Workbench uses KB-scoped live `/investigation/*` graph APIs. Dashboard, alerts, cases, and some analytics/evidence surfaces still include seeded/demo read models until their live projections are migrated.

### 8.2 Page / view structure

```
chili_app/src/
├── main.tsx                    # App entry point
├── App.tsx                     # Root layout, routing
├── lib/
│   ├── apiClient.ts            # Typed fetch wrapper
│   └── queryClient.ts          # TanStack Query client
├── stores/                     # Zustand stores
│   ├── appStore.ts             # Sidebar, selected entity, active KB
│   └── chatStore.ts            # Local chat/session state
├── pages/
│   ├── Dashboard.tsx
│   ├── KnowledgeBaseManager.tsx
│   ├── AlertFeed.tsx
│   ├── InvestigationWorkbench.tsx
│   ├── RagChat.tsx
│   └── ConfigEditor.tsx
├── components/
│   ├── investigation/          # Graph explorer, entity detail, evidence, timeline
│   ├── alerts/                 # Alert list item, badge, detail
│   ├── chat/                   # RAG chat message list, input
│   ├── knowledgebase/          # KB tables, detail view, upload widgets
│   └── common/                 # Shared UI primitives (layout, loading, error)
└── hooks/                      # Shared custom hooks
    ├── useWebSocket.ts
    ├── useDomainConfig.ts
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

- The FastAPI backend auto-generates an OpenAPI specification.
- The current frontend uses typed fetch helpers plus TanStack Query hooks. Generated OpenAPI clients remain an optional hardening path via the existing codegen command.
- TanStack Query wraps all API calls, providing caching, background refetching, and optimistic updates.
- The realtime workspace stream uses `GET /events/stream` as Server-Sent Events. Snapshots include live active-alert counts from the API alert projection, live running-workflow counts from `AgentServiceProtocol`, and live KB statuses from the repository-backed KB projection. In the dev stack, API and worker share workflow lifecycle state through Redis.
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

ingestion:
  sources:
    - type: file_upload
      formats: [pdf, docx, txt, csv, json]
    - type: api_push
      format: json
      endpoint: /ingest/claims

alerts:
  thresholds:
    provider:
      risk_score: 0.75
      anomaly_sigma: 2.5
    beneficiary:
      risk_score: 0.80
    claim:
      amount_percentile: 99
```

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
- **API** exposes `GET /config/domain` so the frontend can read the active configuration.
- **Frontend** reads config at startup and caches it. All entity labels, icons, available panels, and feature gates are driven by this config.

### 9.3 Reconfiguring for a new domain

To retarget chiliAI from Medicare fraud to food supply chain monitoring:

1. Write a new domain config YAML (e.g., `food_supply_chain.yaml`) defining entities like `supplier`, `shipment`, `inspection`, `facility`, and relationships like `shipped_by`, `inspected_at`.
2. Set the active config in the deployment's environment or config path.
3. Restart the backend. The frontend picks up the new config on next load.
4. Create a new knowledge base and ingest domain-relevant documents.

No application code changes required — only the configuration file.

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
      - CHILI_CONFIG_PATH=/config/medicare_fraud.yaml
      - CHILI_KB_REPOSITORY_BACKEND=object_store
      - CHILI_WORKFLOW_RUN_STORE_BACKEND=redis
      - REDIS_URL=redis://redis:6379
    depends_on: [redis]
  worker:
    build: ./backend
    command: python -m agent.coordinator  # or dedicated worker entry point
    environment:
      - CHILI_CONFIG_PATH=/config/medicare_fraud.yaml
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
- **Export**: `/metrics` endpoint on API container; Prometheus scrapes it

### 11.3 Distributed tracing

- **Library**: OpenTelemetry SDK
- **Propagation**: W3C Trace Context across HTTP calls and Redis Stream events (trace ID embedded in event metadata)
- **Export**: OTLP to Jaeger, Tempo, or cloud-native tracing backend

### 11.4 Frontend observability

- **Error tracking**: Sentry (or equivalent) for unhandled exceptions and performance monitoring
- **Analytics**: Optional — may add product analytics for usage patterns in the investigation workbench

---

## 12. Security

> **Current state**: Authentication and authorization middleware, `/auth/*` routes, cookie/Bearer token handling, frontend login/session flow, route-level `require_role`, and auth-enabled default-deny startup audit are implemented. Remaining hardening focuses on production IdP profiles, tenant isolation, and resource-level authorization.

### 12.1 Authentication

- **Approach**: Pluggable FastAPI middleware
- **Protocols**: JWT verification with support for OIDC/OAuth2 identity providers
- **Configuration**: Auth enabled/disabled via domain config. When disabled, requests run as an anonymous `viewer`. When enabled, protected routes accept the `chiliai_session` cookie or a Bearer token.
- **Token flow**: The frontend uses a BFF-style cookie session; Bearer tokens remain supported for API clients.

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
| **Frontend routing** | React Router v7 | Client-side navigation |
| **Server state (FE)** | TanStack Query | API data fetching, caching, invalidation |
| **Client state (FE)** | Zustand | Lightweight UI state |
| **Graph visualization** | `react-force-graph-2d` | Interactive graph explorer in the current prototype |
| **Backend language** | Python 3.12 | All backend services |
| **API framework** | FastAPI | HTTP + WebSocket gateway |
| **Type checking** | pyright (strict mode) | Static type analysis |
| **Testing** | pytest + coverage | Unit/integration tests, ≥85% coverage |
| **Event streaming** | Redis 7+ Streams | Pipeline orchestration, decoupling |
| **Graph database** | in-memory / Neo4j | Knowledge graph storage (pluggable through the graph repository protocol) |
| **Vector store** | in-memory / Qdrant | Embedding storage, similarity search (pluggable through the vector store protocol) |
| **LLM integration** | OpenAI / Anthropic / Ollama / vLLM | RAG answers, entity extraction (pluggable) |
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
| **Authentication & RBAC** | Pluggable auth middleware, role enforcement. See §12. | High — implement before any multi-user deployment |
| **Multi-tenancy** | Tenant-isolated data, config, and KB namespaces. | Medium — after auth |
| **Configuration UI wizard** | Browser-based domain configuration editor instead of manual YAML editing. | Medium |
| **Model training pipeline** | Scheduled/triggered GNN training, embedding fine-tuning. | Medium |
| **Audit log** | Track all analyst actions (graph queries, alert acks, config changes) for compliance. | Medium |
| **Export / reporting** | Generate PDF/CSV reports of investigations, evidence packs, risk summaries. | Low — after core workbench is functional |
| **Plugin system** | Allow third-party analytics modules to be added without modifying core. | Low — after architecture stabilizes |

### 14.3 Current state vs. target

> **Last updated**: April 2026. For implementation status, verify the current code and tests first. Historical status reports and planning docs live under [`docs/archive/`](archive/); use [`todos_and_stubs_audit_2026-05-05.md`](todos_and_stubs_audit_2026-05-05.md) for the current TODO/stub inventory.

| Component | Current state | Next milestone |
|-----------|---------------|----------------|
| `backend/` | Active FastAPI/worker prototype with domain config, typed shared contracts, event bus, ingestion, graph/vector/embedding/LLM/RAG services, analytics modules, monitoring, storage adapters, auth/RBAC middleware, route-level guards, live KB metadata projection, worker-updated workflow lifecycle tracking, SSE workspace snapshots, and in-memory plus selected production-facing adapters | Add a production-grade KB metadata adapter/migration path, complete vector/document provenance cleanup, add production-mode adapter guardrails, and add audit-grade workflow history |
| `chili_app/` | Routed React 19 analyst workbench prototype with Dashboard, Knowledge Base Manager/detail/upload UI, Alert Feed, live KB-scoped Investigation Workbench, RAG Chat, Configuration Editor, and realtime SSE hook | Complete persisted evidence-pack surface, config save endpoint integration, migrate remaining seeded read models to live projections, and production UX/performance polish |
| `docs/` | Architecture, onboarding guide, security checklist, current TODO/stub audit, and archived historical planning/status material | Keep active docs synchronized with implementation and archive stale snapshots |
| `infra/` | Docker Compose, flat Kubernetes manifests, and Helm chart | Add cloud-provider Terraform/Pulumi and production hardening as needed |
| Testing | Extensive backend pytest suite and frontend Vitest suite | Keep CI coverage gates calibrated and add live adapter profiles where services are available |
| CI/CD | GitHub Actions baseline exists | Add deployment/promotion workflows after release environments are defined |
