# Module Map

**Generated:** 2026-05-22 (merge commit `acae4ac`)
**Reviewed:** 2026-05-28 against the current working tree for docs-keeper consistency cleanup.

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
Time-series anomaly detection. Adapters: `InMemoryTimeSeriesStore`, `PostgresObservationStore` / `PostgresObservationSource`.

### `gnn/`
Graph neural network analysis (link prediction, clustering). Adapter: `InMemoryGnnAdapter`.

### `risk/`
Risk scoring. Adapters: `InMemoryRiskStore`, `PostgresRiskHistoryStore` (writer-only + `load_historical_score`).

### `explainability/`
Evidence pack generation. Adapters: `InMemoryExplainabilityStore`, `ShapExplainabilityAdapter`.

### `metrics/`
Entity-metric persistence (no service, no events). Adapters: `InMemoryEntityMetricRepository`, `PostgresEntityMetricRepository`. Throttled per-KB via `MetricsRecomputeThrottle`.

**Forbidden dependencies:** `api`, `ingestion`, other analytics sub-modules (cross-sub-module interaction via events only)

---

## `agent/` — Workflow Coordinator

**Purpose:** Pipeline worker. Consumes Redis Streams events, runs multi-step handlers, tracks lifecycle state.

**Entry point:** `python -m agent.coordinator`

**Pipeline handlers:**
- `handle_documents_uploaded` — document ingestion pipeline (parse → chunk → extract → upsert graph → embed → index)
- `handle_records_ingested` — maps raw records to entities/relationships → graph upsert + vector embed/index [enhanced 2026-05-22 to add embed+index step]
- `handle_knowledge_base_deleted` — full 4-step retry cascade (graph → vector → raw_records → object_store) [added 2026-05-22]
- `handle_graph_updated_for_analytics` (Flow 2) — graph-metric persistence to Postgres
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

**Config files:** `defaults/medicare_fraud.yaml`, `defaults/medicare_fraud_dev.yaml`, `defaults/medicare_fraud_cms_desynpuf.yaml`, `defaults/food_supply_chain.yaml`

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

## `tools/sample_data/` — Data Preparation CLI

**Purpose:** Filter and transform CMS source data for local development and demo.

**Tools:** `build_tennessee_subset.py` — filters NPPES (by state) and DE-SynPUF (cross-filtered by NPI) to a deterministic Tennessee subset. See `tooling-inventory.md`.

---

## `scripts/` — Shell Drivers

**Purpose:** Convenience scripts for local demo flows.

**Scripts:** `demo_ingest_tn_subset.sh` — drives `make demo-tn-subset`. `smoke_graph_workflow.sh` — end-to-end smoke test.
