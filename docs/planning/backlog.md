# chiliAI — Full Project Backlog

> **Generated**: April 17, 2026
> **Basis**: [Project Status Report](../project_status_report.md)
> **Authors**: Requirements Engineer Agent + Software Design Expert Agent
> **Format**: User stories with acceptance criteria, priority, size, and dependency tracking

---

## Backlog Summary

| Epic | Title | Stories | P0 | P1 | P2 | P3 |
|------|-------|---------|----|----|----|----|
| E1 | Foundation & Shared Infrastructure | 10 | 3 | 4 | 3 | 0 |
| E2 | Graph Module Completion | 6 | 3 | 2 | 1 | 0 |
| E3 | Production Adapters (Vector, Embeddings, LLM, Storage) | 8 | 1 | 3 | 3 | 0 |
| E4 | Pipeline Completion (Agent Coordinator) | 8 | 2 | 4 | 2 | 0 |
| E5 | API Routers | 14 | 0 | 8 | 5 | 1 |
| E6 | RAG Pipeline | 8 | 3 | 3 | 2 | 0 |
| E7 | Analytics Suite | 12 | 1 | 4 | 5 | 2 |
| E8 | Monitoring & Alerting | 8 | 0 | 4 | 3 | 0 |
| E9 | Frontend Application | 13 | 2 | 8 | 2 | 0 |
| E10 | Quality, Security & Operations | 15 | 3 | 9 | 2 | 0 |
| **Total** | | **102** | **18** | **49** | **26** | **3** |

### Priority Definitions

| Priority | Meaning |
|----------|---------|
| **P0** | Architectural blocker — blocks multiple downstream stories |
| **P1** | Core capability — required for MVP feature completeness |
| **P2** | Important enhancement — improves quality, UX, or operational readiness |
| **P3** | Nice-to-have — can be deferred without impacting release |

### Size Definitions

| Size | Effort Estimate |
|------|----------------|
| **XS** | < 0.5 day |
| **S** | 0.5–1 day |
| **M** | 2–3 days |
| **L** | 4–6 days |
| **XL** | 1–2 weeks |

---

## Epic 1: Foundation & Shared Infrastructure

> Harden the shared types, utility layer, configuration schema, dependency injection, and event envelope so that all downstream modules build on a consistent, auditable, config-driven foundation.

### E1-S01: Add audit and versioning fields to Entity

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** `Entity` to carry `created_at`, `updated_at`, and `version` fields, **so that** graph merge logic can detect changes and enforce optimistic concurrency control.

**Acceptance Criteria:**
1. `Entity` in `shared/types.py` has `created_at: datetime`, `updated_at: datetime | None = None`, and `version: int = 1`.
2. `created_at` defaults to UTC now via the shared `utc_now()` utility (see E1-S03).
3. Existing tests that construct `Entity` instances still pass (fields have defaults).
4. `validate_entity()` does not validate audit fields against `PropertyDefinition` — they are platform-owned, not domain-owned.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E1-S03 |

**Notes:** These fields are consumed by graph upsert idempotency (E2-S05), alert lifecycle, and future RBAC audit logs.

---

### E1-S02: Add audit and versioning fields to Relationship

Status: Complete on April 20, 2026.

**As a** platform developer, **I want** `Relationship` to carry `created_at`, `updated_at`, `version`, and an optional `weight` field, **so that** relationship upserts support concurrency control and weighted graph algorithms.

**Acceptance Criteria:**
1. `Relationship` in `shared/types.py` has `created_at: datetime`, `updated_at: datetime | None = None`, `version: int = 1`, and `weight: float | None = None`.
2. `created_at` defaults to UTC now via the shared utility.
3. All existing tests that construct `Relationship` instances still pass.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E1-S03 |

**Notes:** `weight` enables PageRank and betweenness centrality in the analytics module.

---

### E1-S03: Consolidate `_utc_now()` into `shared/utils.py`

Status: Complete on April 20, 2026.

**As a** platform developer, **I want** a single `utc_now()` function in `shared/utils.py` replacing the duplicated `_utc_now()` definitions across 9+ modules, **so that** timestamp generation has one canonical source and can be patched in a single place during tests.

**Acceptance Criteria:**
1. `shared/utils.py` exports `utc_now() -> datetime` returning `datetime.now(timezone.utc)`.
2. Every module-local `_utc_now()` (events/types.py, graph/models.py, graph/service_models.py, vectorstore/models.py, vectorstore/service_models.py, llm/models.py, agent/models.py, ingestion/service_models.py, embeddings/models.py, monitoring/models.py, ingestion/chunker.py) is replaced with an import from `shared.utils`.
3. All existing tests pass without changes to assertions.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | None |

**Notes:** grep for `_utc_now` to find all occurrences. This is a mechanical refactor — each replacement is a one-line import swap.

---

### E1-S04: Add graph database configuration section to DomainConfig

Status: Complete on April 20, 2026.

**As a** platform operator, **I want** a `GraphDbConfig` section in the domain configuration, **so that** the graph adapter backend, connection URI, and pool settings are selected from config instead of hardcoded.

**Acceptance Criteria:**
1. `config/schema.py` defines `GraphDbConfig` with fields: `backend: Literal["neo4j", "memgraph", "in_memory"]`, `uri: str | None`, `pool_size: int = 10`, `auth_env_var: str | None`.
2. `DomainConfig` has an optional `graph: GraphDbConfig | None = None` field.
3. Config loading defaults to `in_memory` when the section is absent.
4. The default YAML fixture in `config/defaults/` is updated with a commented example.
5. Unit test validates round-trip serialize/deserialize of the new section.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** This is the first of eight subsystem config sections. Each follows the same pattern. Keep `backend` as a Literal to enable pyright exhaustiveness checks when selecting adapters.

---

### E1-S05: Add vector store configuration section to DomainConfig

Status: Complete on April 20, 2026.

**As a** platform operator, **I want** a `VectorStoreConfig` section in the domain configuration, **so that** the vector store backend, connection, and dimensionality are config-driven.

**Acceptance Criteria:**
1. `config/schema.py` defines `VectorStoreConfig` with fields: `backend: Literal["qdrant", "pgvector", "in_memory"]`, `uri: str | None`, `dimensions: int = 384`, `distance_metric: Literal["cosine", "dot", "euclidean"] = "cosine"`.
2. `DomainConfig` has `vectorstore: VectorStoreConfig | None = None`.
3. Config loading defaults to `in_memory` when absent.
4. Unit test validates the new section.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** `dimensions` must match the embedding model output size. Cross-validation with `EmbeddingsConfig.dimensions` is deferred to E1-S06.

---

### E1-S06: Add LLM, embeddings, storage, events, monitoring, and RAG configuration sections to DomainConfig

Status: Complete on April 20, 2026.

**As a** platform operator, **I want** configuration sections for LLM, embeddings, object storage, events, monitoring, and RAG, **so that** every external subsystem is configurable from a single YAML surface.

**Acceptance Criteria:**
1. `config/schema.py` defines: `LlmConfig` (provider, model, api_key_env_var, temperature, max_tokens), `EmbeddingsConfig` (provider, model, dimensions, batch_size), `ObjectStoreConfig` (backend, bucket, base_path, credentials_env_var), `EventBusConfig` (backend, uri, stream_prefix, consumer_group), `MonitoringConfig` (evaluation_interval_seconds, dedup_window_seconds, max_alerts_per_entity), `RagConfig` (top_k, expansion_depth, reranking_enabled, system_prompt_template).
2. Each section is an optional field on `DomainConfig` that defaults to a sensible in-memory/local value.
3. `schema_version: str = "1.0"` is added to `DomainConfig` for future migration support.
4. Cross-field validator ensures `EmbeddingsConfig.dimensions == VectorStoreConfig.dimensions` when both are present.
5. All existing config tests pass unchanged.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S04, E1-S05 |

**Notes:** `EventBusConfig` absorbs the settings currently in `events/runtime.py:EventBusSettings`. Keep backwards compatibility — if absent, fall back to environment variables as today.

---

### E1-S07: Config-driven adapter selection in the DI layer

Status: Complete on April 20, 2026.

**As a** platform developer, **I want** `api/dependencies.py` to select adapter implementations based on `DomainConfig` subsystem sections, **so that** switching from in-memory to production adapters requires only a config change — no code edits.

**Acceptance Criteria:**
1. For each subsystem (`graph`, `vectorstore`, `embeddings`, `llm`, `storage`, `events`, `monitoring`), `api/dependencies.py` contains a factory that reads the corresponding `DomainConfig` section and returns the appropriate adapter or service instance.
2. When a config section is absent, the factory defaults to the in-memory/local adapter path.
3. Factory functions exist for `get_graph_service()`, `get_vectorstore_service()`, `get_embeddings_service()`, `get_llm_service()`, `get_monitoring_service()`, while preserving existing `get_object_store()` and `get_event_bus()` call sites.
4. Each factory raises a clear `ConfigurationError` if the requested backend is not yet implemented.
5. Existing tests that rely on in-memory defaults still pass.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S06 |

**Notes:** Use a simple match/case on the backend literal. Do not introduce a plugin registry — YAGNI at this stage. Worker (`agent/coordinator.py`) should be updated in a follow-up (E4-S01) to share the same config-driven wiring.

---

### E1-S08: Enrich event envelope with correlation_id, source, and schema_version

Status: Complete on April 20, 2026.

**As a** platform developer, **I want** every event to carry a `correlation_id`, `source`, and `schema_version`, **so that** distributed traces can be correlated end-to-end and event consumers can handle envelope evolution gracefully.

**Acceptance Criteria:**
1. `EventBase` in `events/types.py` has `correlation_id: str` (defaults to `generate_id()`), `source: str | None = None`, `schema_version: int = 1`.
2. Worker pipeline handlers propagate `correlation_id` from the incoming event to all downstream events published within the same pipeline run.
3. Existing event construction (tests, coordinator) still works — all new fields have defaults.
4. At least one test verifies correlation_id propagation across two pipeline stages.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** `source` identifies which service/container produced the event (e.g., "chili-api", "chili-worker"). `schema_version` enables future envelope migrations without breaking consumers.

---

### E1-S09: Add updated_at and status enrichment to KnowledgeBase

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** `KnowledgeBase` to carry `updated_at` and richer status lifecycle fields, **so that** the KB listing endpoint can show accurate last-modified timestamps and status progression.

**Acceptance Criteria:**
1. `KnowledgeBase` in `shared/types.py` has `updated_at: datetime | None = None`.
2. `status` field type is narrowed to `Literal["active", "building", "ready", "error", "archived"]` with default `"active"`.
3. Existing tests pass.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | XS | None |

**Notes:** The `kb.ready` event (E4-S03) will set status to "ready" once the full pipeline completes.

---

### E1-S10: Add structured fields to EvidencePack and Alert

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** `EvidencePack` to carry `created_at` and `source_documents`, and `Alert` to carry `updated_at`, `resolved_by`, and `resolution_notes`, **so that** the alert investigation UI has sufficient metadata for audit and resolution tracking.

**Acceptance Criteria:**
1. `EvidencePack` has `created_at: datetime` (defaulting to utc_now) and `source_documents: list[str] = Field(default_factory=list)`.
2. `Alert` has `updated_at: datetime | None = None`, `resolved_by: str | None = None`, `resolution_notes: str | None = None`, and `status: Literal["open", "acknowledged", "investigating", "resolved", "dismissed"] = "open"`.
3. All existing tests pass.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E1-S03 |

**Notes:** The `severity` field TODO for a proper enum remains deferred to a later story.

---

## Epic 2: Graph Module Completion

> Extend the write-only graph module with query capabilities, transaction semantics, and a production adapter so that the investigation workbench, dashboard, and RAG chat can read graph data.

### E2-S01: Extend GraphRepository protocol with read/query methods

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** the `GraphRepository` protocol to define `get_entity`, `get_neighbors`, `get_entities_by_type`, `search_entities`, `count_entities`, `count_relationships`, and `delete_entity`, **so that** all graph adapters provide a consistent query surface.

**Acceptance Criteria:**
1. `graph/adapters/protocols.py` adds: `get_entity(kb_id, entity_id) -> Entity | None`, `get_neighbors(kb_id, entity_id, depth: int, direction: Literal["in", "out", "both"]) -> SubgraphResult`, `get_entities_by_type(kb_id, entity_type, limit, offset) -> list[Entity]`, `search_entities(kb_id, query: str, limit) -> list[Entity]`, `count_entities(kb_id) -> int`, `count_relationships(kb_id) -> int`, `delete_entity(kb_id, entity_id) -> None`, `delete_relationship(kb_id, relationship_id) -> None`.
2. `graph/models.py` defines `SubgraphResult` (entities: list[Entity], relationships: list[Relationship]) and `GraphMetrics` (entity_count, relationship_count, avg_degree).
3. Protocol is `@runtime_checkable`.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | None |

**Notes:** `SubgraphResult` is reused by the investigation workbench neighborhood query and RAG context expansion.

---

### E2-S02: Implement read/query methods on InMemoryGraphRepository

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** the in-memory graph adapter to implement all query methods from the extended protocol, **so that** tests and local development can exercise the full graph surface without a database.

**Acceptance Criteria:**
1. `InMemoryGraphRepository` implements every method added in E2-S01.
2. `get_neighbors` performs a BFS up to `depth` hops, respecting `direction`.
3. `search_entities` does a case-insensitive substring match on entity properties.
4. `delete_entity` also removes relationships referencing the deleted entity.
5. Unit tests cover each method (happy path + edge cases: missing entity, empty graph, depth=0).
6. Coverage ≥ 85% for the graph module.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E2-S01 |

**Notes:** The BFS implementation for `get_neighbors` needs to build an adjacency index on first access. Consider lazy indexing.

---

### E2-S03: Extend GraphServiceProtocol and GraphService with query methods

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** the graph service to expose `get_entity`, `query_neighborhood`, `search_entities`, `get_subgraph`, and `compute_metrics` through the service protocol, **so that** API routers and the RAG module can query the graph through a clean service boundary.

**Acceptance Criteria:**
1. `graph/protocols.py:GraphServiceProtocol` adds: `get_entity(kb_id, entity_id) -> Entity | None`, `query_neighborhood(kb_id, entity_id, depth) -> SubgraphResult`, `search_entities(kb_id, query, limit, offset) -> list[Entity]`, `compute_metrics(kb_id) -> GraphMetrics`.
2. `graph/service.py:GraphService` implements all new methods by delegating to `GraphRepository`.
3. `graph/service_models.py` defines request/response models: `NeighborhoodQuery`, `EntitySearchQuery`, `GraphMetricsResult`.
4. Unit tests verify each service method delegates correctly.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E2-S01, E2-S02 |

**Notes:** Service methods should validate `depth` (max 5) and `limit` (max 500) to prevent runaway queries.

---

### E2-S04: Neo4j production graph adapter

**Status:** Complete on April 20, 2026.

**As a** platform operator, **I want** a Neo4j adapter implementing `GraphRepository`, **so that** the platform can persist graph data durably with Cypher query capabilities.

**Acceptance Criteria:**
1. `graph/adapters/neo4j_adapter.py` implements every `GraphRepository` method using the `neo4j` Python driver.
2. Connection pooling is configured via `GraphDbConfig.pool_size`.
3. `get_neighbors` uses variable-length Cypher path patterns for efficient traversal.
4. `upsert_entities` and `upsert_relationships` use `MERGE` statements for idempotency.
5. Integration test (marked `@pytest.mark.integration`) validates round-trip CRUD against a test Neo4j instance.
6. `neo4j` is listed as an optional dependency in `pyproject.toml` under `[project.optional-dependencies]`.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E2-S01, E1-S04 |

**Notes:** Use `neo4j` driver ≥ 5.x. Parameterize all Cypher queries — never interpolate entity IDs into query strings. The integration test can use `testcontainers` or skip if Neo4j is unavailable.

---

### E2-S05: Add transaction semantics to graph upsert

**Status:** Complete on April 20, 2026.

**As a** platform developer, **I want** entity and relationship upserts within a single `GraphBuildTask` to execute atomically, **so that** a failure mid-upsert does not leave the graph in an inconsistent state.

**Acceptance Criteria:**
1. `GraphRepository` protocol adds a context-manager method `transaction(kb_id) -> AbstractContextManager` (or equivalent).
2. `GraphService.upsert_task` wraps entity + relationship upserts in a single transaction scope.
3. If relationship upsert fails, entity upsert is rolled back.
4. In-memory adapter implements transaction via a snapshot-and-restore mechanism.
5. Neo4j adapter delegates to a driver-level transaction.
6. Test verifies rollback: inject a failure during relationship upsert and confirm entities are not persisted.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E2-S02, E2-S04 |

**Notes:** For the in-memory adapter, deepcopy the affected buckets before the operation and restore on failure.

---

### E2-S06: Batch chunking for large graph upserts

**As a** platform developer, **I want** `GraphService.upsert_task` to split large entity/relationship lists into configurable batch sizes, **so that** oversized documents do not cause transaction timeouts or memory spikes.

**Acceptance Criteria:**
1. `GraphService` accepts a `batch_size: int = 500` constructor parameter.
2. Entities and relationships are chunked into batches of `batch_size` and upserted sequentially, each in its own transaction.
3. If a batch fails, an error is raised with the count of successfully upserted entities before the failure.
4. Test with 1500 entities and batch_size=500 verifies three batches execute.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E2-S05 |

**Notes:** Batch boundaries are per-transaction. This trades full atomicity for practical operability on large documents.

**Status:** Complete. `GraphService` now batches entity and relationship upserts by constructor-configured size and raises partial-progress errors without rolling back earlier committed batches.

---

## Epic 3: Production Adapters (Vector, Embeddings, LLM, Storage)

> Implement concrete adapters for external systems behind existing protocol boundaries so the platform can graduate from in-memory stubs to production-grade infrastructure.

### E3-S01: Qdrant vector store adapter

**Status:** Complete on April 20, 2026.

**As a** platform operator, **I want** a Qdrant adapter implementing `VectorStoreProtocol`, **so that** vector similarity search is backed by a scalable, production-grade engine.

**Acceptance Criteria:**
1. `vectorstore/adapters/qdrant_adapter.py` implements `VectorStoreProtocol` (upsert_records, search, delete_records).
2. Connection is configured via `VectorStoreConfig` (uri, distance_metric).
3. Collections are created per `knowledge_base_id` with the configured `dimensions` and `distance_metric`.
4. `search` supports metadata filter translation to Qdrant filter syntax.
5. `qdrant-client` is listed as an optional dependency.
6. Integration test (marked `@pytest.mark.integration`) verifies upsert → search round-trip.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S05 |

**Notes:** Use `qdrant_client.QdrantClient` with gRPC transport for performance. Parameterize collection naming as `chili_{knowledge_base_id}` to avoid collisions.

**Implementation note:** The adapter provides `delete_records` as an adapter-local method to satisfy the story requirement while preserving the current `VectorStoreProtocol` contract unchanged.

---

### E3-S02: Sentence-Transformers embeddings adapter

**As a** platform developer, **I want** an embeddings adapter using `sentence-transformers`, **so that** the platform can generate high-quality local embeddings without external API calls.

**Acceptance Criteria:**
1. `embeddings/adapters/sentence_transformers_adapter.py` implements the embeddings protocol: `embed(EmbeddingRequest) -> EmbeddingResult`.
2. Model is loaded once at construction and reused.
3. Batching respects `EmbeddingsConfig.batch_size` — large requests are split internally.
4. The adapter normalizes output vectors to unit length for cosine similarity.
5. `sentence-transformers` is listed as an optional dependency.
6. Unit test uses a small model (`all-MiniLM-L6-v2`) and verifies output dimensions and non-zero vectors.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S06 |

**Notes:** Default model should be configurable via `EmbeddingsConfig.model`. GPU vs CPU fallback should be automatic via PyTorch.

---

### E3-S03: OpenAI embeddings adapter

**As a** platform developer, **I want** an embeddings adapter calling the OpenAI Embeddings API, **so that** operators can use cloud-hosted embedding models when local GPU is unavailable.

**Acceptance Criteria:**
1. `embeddings/adapters/openai_adapter.py` implements the embeddings protocol.
2. API key is read from the environment variable specified in `EmbeddingsConfig.api_key_env_var`.
3. Batching respects the OpenAI per-request token limit (8191 tokens for `text-embedding-3-small`).
4. Rate-limit errors (HTTP 429) trigger exponential backoff retry (max 3 attempts).
5. `openai` is listed as an optional dependency.
6. Unit test mocks the OpenAI client and verifies correct request construction and response parsing.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E1-S06 |

**Notes:** Support both `text-embedding-3-small` and `text-embedding-3-large` via config. Never log API keys.

---

### E3-S04: OpenAI LLM adapter

**As a** platform developer, **I want** an LLM adapter calling the OpenAI Chat Completions API, **so that** the RAG chat and analytics explainability modules can generate natural-language outputs.

**Acceptance Criteria:**
1. `llm/adapters/openai_adapter.py` implements the LLM protocol: `generate(GenerationRequest) -> GenerationResult`.
2. API key is read from the environment variable specified in `LlmConfig.api_key_env_var`.
3. Token usage (prompt_tokens, completion_tokens) is captured in `CompletionMetadata`.
4. Rate-limit errors trigger exponential backoff retry (max 3 attempts).
5. `openai` is listed as an optional dependency (shared with E3-S03).
6. Unit test mocks the OpenAI client and verifies request/response mapping.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S06 |

**Notes:** Support `gpt-4o`, `gpt-4o-mini` via config. Do not implement streaming in this story — see E5-S04 for SSE streaming.

---

### E3-S05: Anthropic LLM adapter

**As a** platform developer, **I want** an LLM adapter calling the Anthropic Messages API, **so that** operators have a second LLM vendor option.

**Acceptance Criteria:**
1. `llm/adapters/anthropic_adapter.py` implements the LLM protocol.
2. API key is read from the configured environment variable.
3. Anthropic's `input_tokens` and `output_tokens` are mapped to `CompletionMetadata`.
4. Rate-limit handling with retry.
5. `anthropic` is listed as an optional dependency.
6. Unit test mocks the Anthropic client.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E1-S06 |

**Notes:** Support `claude-sonnet-4-20250514` and `claude-3-5-haiku-20241022` via config.

---

### E3-S06: S3/MinIO object storage adapter

**As a** platform operator, **I want** an object storage adapter using the S3 API, **so that** document artifacts, chunking results, and graph snapshots are persisted durably.

**Acceptance Criteria:**
1. `storage/adapters/s3_adapter.py` implements `ObjectStore` protocol: `put_bytes`, `get_bytes`, `delete`, `exists`, `list_keys`.
2. Connection is configured via `ObjectStoreConfig` (endpoint_url for MinIO compatibility, bucket, credentials_env_var).
3. Metadata is stored as S3 object metadata headers.
4. `boto3` is listed as an optional dependency.
5. Integration test validates put → get → delete round-trip using `moto` mock.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S06 |

**Notes:** Use `boto3` with `endpoint_url` override for MinIO. All keys should be prefixed with a configurable namespace to support multi-tenant buckets.

---

### E3-S07: Local filesystem object storage adapter

**As a** platform developer, **I want** a local filesystem adapter implementing `ObjectStore`, **so that** developers can run the full pipeline locally without S3/MinIO.

**Acceptance Criteria:**
1. `storage/adapters/local_fs_adapter.py` implements `ObjectStore` protocol.
2. Objects are stored as files under a configurable base directory (default: `./data/objects/`).
3. Metadata is stored in a sidecar `.meta.json` file alongside each object.
4. `list_keys` supports prefix-based listing.
5. File paths are sanitized to prevent directory traversal (reject keys containing `..` or absolute paths).
6. Unit tests cover put/get/delete/list/exists and path-traversal rejection.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | None |

**Notes:** This adapter requires no external dependencies. Use `pathlib.Path` for safe path construction.

---

### E3-S08: Extend ObjectStore protocol with delete, exists, list_keys

**As a** platform developer, **I want** the `ObjectStore` protocol to include `delete(key)`, `exists(key) -> bool`, and `list_keys(prefix) -> list[str]`, **so that** all storage adapters provide a complete interface for lifecycle management.

**Acceptance Criteria:**
1. `storage/protocols.py` adds `delete`, `exists`, and `list_keys` to the `ObjectStore` protocol.
2. `InMemoryObjectStore` implements all three new methods.
3. Existing tests pass; new unit tests cover each method on the in-memory adapter.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | None |

**Notes:** This unblocks E3-S06, E3-S07, and the KB delete endpoint (E5-S12).

---

## Epic 4: Pipeline Completion (Agent Coordinator)

> Wire the remaining pipeline stages (embeddings, vector indexing, kb.ready) and add operational resilience (dead-letter queue, retry tracking, graceful shutdown, health check) to the worker coordinator.

### E4-S01: Wire embeddings step after graph.updated

**As a** platform developer, **I want** the worker coordinator to consume `graph.updated` events, generate embeddings for upserted entities, and publish an `embeddings.complete` event, **so that** the pipeline progresses from graph to vector indexing.

**Acceptance Criteria:**
1. `agent/coordinator.py` registers a handler for `GraphUpdatedEvent`.
2. The handler loads the graph update artifact from object storage, retrieves entity texts, calls the embeddings service, and persists `EmbeddingResult` to object storage.
3. An `EmbeddingsCompleteEvent` is published with the embeddings storage key and entity count.
4. `events/types.py` defines `EmbeddingsCompleteEvent` with appropriate reference model.
5. Unit test verifies the handler chains correctly with in-memory adapters.
6. `correlation_id` is propagated from the incoming event.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E1-S08 |

**Notes:** Entity text for embedding should be constructed by concatenating `entity.type` + key properties. The exact text template can be a simple f-string for now.

---

### E4-S02: Wire vector indexing step after embeddings.complete

**As a** platform developer, **I want** the worker coordinator to consume `embeddings.complete` events, upsert vectors into the vector store, and publish a `vectors.indexed` event, **so that** similarity search becomes available after embedding.

**Acceptance Criteria:**
1. `agent/coordinator.py` registers a handler for `EmbeddingsCompleteEvent`.
2. The handler loads `EmbeddingResult` from storage, constructs `VectorRecord` instances with entity metadata, and calls `VectorStoreProtocol.upsert_records`.
3. A `VectorsIndexedEvent` is published upon success.
4. `events/types.py` defines `VectorsIndexedEvent`.
5. Unit test verifies the handler with in-memory vector store and embedder.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E4-S01 |

**Notes:** Vector metadata should include `knowledge_base_id`, `entity_id`, `entity_type` to support filtered search in the RAG module.

---

### E4-S03: Emit kb.ready event at pipeline completion

**As a** platform developer, **I want** the worker to emit a `kb.ready` event after `vectors.indexed`, **so that** the frontend can display knowledge base readiness status and trigger downstream analytics.

**Acceptance Criteria:**
1. `agent/coordinator.py` registers a handler for `VectorsIndexedEvent`.
2. The handler publishes a `KnowledgeBaseReadyEvent` containing `knowledge_base_id`, total entity count, relationship count, and vector count.
3. `events/types.py` defines `KnowledgeBaseReadyEvent`.
4. If a KnowledgeBase record store is available, the handler updates KB status to `"ready"`.
5. Unit test verifies the full pipeline chain from `documents.uploaded` through `kb.ready`.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E4-S02, E1-S09 |

**Notes:** This is the terminal event for the ingestion pipeline. Downstream consumers (analytics, monitoring) can subscribe to this event.

---

### E4-S04: Dead-letter queue handling for failed pipeline events

**As a** platform operator, **I want** events that fail processing after exhausting retries to be moved to a dead-letter stream, **so that** failed work is preserved for inspection and replay without blocking the main pipeline.

**Acceptance Criteria:**
1. `events/protocols.py` adds a `publish_to_dlq(event, error_info)` method to the `EventBus` protocol.
2. The in-memory adapter records DLQ entries in a separate list accessible for testing.
3. The Redis Streams adapter publishes to a `{stream_name}.dlq` stream.
4. The coordinator wraps each handler in a try/except: on failure, the event + error details are sent to DLQ.
5. DLQ entries include: original event payload, error message, traceback, timestamp, retry count.
6. Unit test verifies a failing handler routes the event to DLQ after retries are exhausted.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E4-S05 |

**Notes:** DLQ replay is a separate future story. This story only handles capture.

---

### E4-S05: Retry count tracking with exponential backoff

**As a** platform operator, **I want** the worker coordinator to retry failed pipeline steps with exponential backoff and a configurable max retry count, **so that** transient failures (network blips, API rate limits) are handled automatically.

**Acceptance Criteria:**
1. The coordinator wraps each event handler with retry logic: max retries configurable (default 3), exponential backoff (1s, 2s, 4s).
2. Retry count is tracked per event (via `correlation_id` or event ID).
3. After max retries, the event is routed to the dead-letter queue.
4. Each retry attempt logs: event type, correlation_id, attempt number, delay, error message.
5. Unit test verifies: transient failure retries succeed on second attempt; permanent failure exhausts retries.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | None |

**Notes:** Keep retry state in-process for now (dict keyed by event ID). A persistent retry store can be added later for multi-worker coordination.

---

### E4-S06: Graceful shutdown for the worker process

**As a** platform operator, **I want** the worker to handle SIGTERM/SIGINT gracefully by finishing the current event before exiting, **so that** container orchestrators can stop workers without corrupting in-flight work.

**Acceptance Criteria:**
1. `agent/coordinator.py` registers signal handlers for SIGTERM and SIGINT.
2. On signal receipt, the worker sets a shutdown flag and stops polling for new events.
3. The currently processing event (if any) completes before the process exits.
4. Logging outputs "Shutdown requested, finishing current event..." and "Worker stopped gracefully."
5. Test simulates shutdown during processing and verifies the in-flight event completes.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** The `run_worker` loop currently uses `asyncio.sleep` — convert the shutdown flag to an `asyncio.Event`.

---

### E4-S07: Worker health check endpoint

**As a** platform operator, **I want** the worker process to expose a lightweight health check on a configurable HTTP port, **so that** container orchestrators (Docker, Kubernetes) can verify worker liveness.

**Acceptance Criteria:**
1. The worker starts a minimal HTTP server (e.g., `aiohttp` or stdlib `http.server`) on port 8001 (configurable).
2. `GET /health` returns `{"status": "ok", "last_event_processed_at": "<ISO timestamp>"}`.
3. If no event has been processed in 5 minutes, status becomes `"degraded"`.
4. The health server runs in a background asyncio task and does not interfere with event processing.
5. Test verifies the health endpoint responds correctly.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | None |

**Notes:** Keep this minimal — no framework dependency. A stdlib `asyncio` HTTP handler is sufficient.

---

### E4-S08: Config-driven adapter wiring in the worker coordinator

**As a** platform developer, **I want** `build_worker_dependencies()` to select adapters from `DomainConfig` instead of hardcoding in-memory implementations, **so that** the worker uses the same config-driven wiring as the API gateway.

**Acceptance Criteria:**
1. `build_worker_dependencies()` reads `DomainConfig` subsystem sections and selects matching adapters for object store, graph repository, embeddings, vector store, and LLM.
2. Falls back to in-memory adapters when config sections are absent (preserving current test behavior).
3. Adapter construction failures raise clear `ConfigurationError` exceptions with the subsystem name and backend value.
4. Unit test verifies that removing a config section falls back to in-memory.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S07 |

**Notes:** Extract a shared `create_adapter(subsystem, config)` utility to avoid duplicating the selection logic between `dependencies.py` and `coordinator.py`.

---

## Epic 5: API Routers

> Build the FastAPI router layer for all frontend-facing capabilities: alerts, investigation, RAG chat, WebSocket hub, analytics, and KB CRUD completion.

### E5-S01: Alerts router — list alerts

**As an** analyst, **I want** to list alerts with filtering by severity, entity type, and status, **so that** I can triage the most critical findings.

**Acceptance Criteria:**
1. `api/routers/alerts.py` defines `GET /alerts` with query params: `severity`, `entity_type`, `status`, `limit` (default 50), `offset` (default 0).
2. Response model: `AlertListResponse(items: list[Alert], total: int)`.
3. Router delegates to an injected alerts service (protocol-based).
4. Returns 200 with empty list when no alerts match.
5. Test verifies filtering and pagination.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E1-S10 |

**Notes:** The alerts service implementation is a later story — this router uses DI and can be tested with a mock service.

---

### E5-S02: Alerts router — acknowledge and resolve alerts

**As an** analyst, **I want** to acknowledge and resolve alerts with optional resolution notes, **so that** my investigation progress is tracked.

**Acceptance Criteria:**
1. `POST /alerts/{alert_id}/acknowledge` sets alert status to `"acknowledged"` and returns the updated alert.
2. `POST /alerts/{alert_id}/resolve` accepts a `ResolutionRequest(notes: str | None, resolved_by: str)` body, sets status to `"resolved"`, and returns the updated alert.
3. Returns 404 if the alert ID does not exist.
4. Returns 409 if the alert is already resolved (cannot re-resolve).
5. Tests cover happy path, 404, and 409 cases.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E5-S01, E1-S10 |

**Notes:** `resolved_by` will come from auth context in production. For now, accept it in the request body.

---

### E5-S03: Investigation router — entity detail and neighborhood query

**As an** analyst, **I want** to retrieve entity details and explore the graph neighborhood around an entity, **so that** I can investigate suspicious patterns visually.

**Acceptance Criteria:**
1. `api/routers/investigation.py` defines `GET /investigation/entities/{entity_id}?kb_id=...` returning the entity with properties.
2. `GET /investigation/entities/{entity_id}/neighborhood?kb_id=...&depth=2` returns `SubgraphResult` (entities + relationships within N hops).
3. `depth` is clamped to a maximum of 5. Values above 5 return 422.
4. Returns 404 if the entity does not exist.
5. Tests cover happy path, missing entity, depth clamping.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E2-S03 |

**Notes:** Router delegates to `GraphService.get_entity` and `GraphService.query_neighborhood`.

---

### E5-S04: Investigation router — search entities

**As an** analyst, **I want** to search for entities by a text query across properties, **so that** I can find persons, organizations, or claims by name or identifier.

**Acceptance Criteria:**
1. `GET /investigation/search?kb_id=...&q=...&limit=20&offset=0` returns `EntitySearchResponse(items: list[Entity], total: int)`.
2. `q` is required; returns 422 if missing.
3. `limit` is clamped to max 500.
4. Router delegates to `GraphService.search_entities`.
5. Test verifies search returns matching entities and respects limit/offset.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E2-S03 |

**Notes:** This is a basic property search. Semantic search (vector similarity on entity embeddings) is a future enhancement.

---

### E5-S05: RAG chat router — send message

**As an** analyst, **I want** to send a natural-language question to a RAG-powered chat endpoint scoped to a knowledge base, **so that** I get answers grounded in ingested data.

**Acceptance Criteria:**
1. `api/routers/chat.py` defines `POST /chat/conversations/{conversation_id}/messages` accepting `ChatMessageRequest(content: str, kb_id: str)`.
2. Router delegates to the RAG service: retrieves relevant context from vector store, constructs a prompt with context + user question, calls LLM, returns `ChatMessageResponse(content: str, sources: list[str])`.
3. Returns 400 if `content` is empty.
4. Returns 404 if `kb_id` references a non-existent knowledge base.
5. Test uses mocked RAG service verifying correct delegation.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S07 |

**Notes:** Non-streaming response in this story. Streaming via SSE is E5-S06.

---

### E5-S06: RAG chat router — streaming response via SSE

**As an** analyst, **I want** the RAG chat response to stream token-by-token via Server-Sent Events, **so that** I see progressive output instead of waiting for the full response.

**Acceptance Criteria:**
1. `POST /chat/conversations/{conversation_id}/messages?stream=true` returns a `StreamingResponse` with `text/event-stream` content type.
2. Each SSE event contains a `data` field with a JSON chunk: `{"token": "...", "done": false}`.
3. The final event has `{"token": "", "done": true, "sources": [...]}`.
4. The LLM adapter protocol defines an optional `generate_stream()` method.
5. Test verifies the SSE format and that all tokens concatenated equal the full response.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E5-S05, E3-S04 |

**Notes:** Use FastAPI `StreamingResponse` with an async generator. SSE reconnection / event IDs are not required for MVP.

---

### E5-S07: WebSocket hub — real-time alerts

**As an** analyst, **I want** to receive new alerts in real-time via WebSocket, **so that** I am immediately notified of high-severity findings without polling.

**Acceptance Criteria:**
1. `api/routers/ws.py` defines `WS /ws/alerts` accepting a WebSocket connection.
2. When a new `AlertCreatedEvent` is published on the event bus, connected clients receive a JSON message with the alert payload.
3. Clients can send a `{"subscribe": {"severity": ["high", "critical"]}}` message to filter by severity.
4. Connection health is maintained via ping/pong every 30 seconds.
5. Test verifies: connect, receive alert, severity filter, disconnect.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E5-S01 |

**Notes:** Use FastAPI WebSocket support. The bridge between event bus and WebSocket clients needs an in-process pub/sub (asyncio.Queue per client).

---

### E5-S08: WebSocket hub — pipeline status

**As an** analyst, **I want** to see pipeline stage progress in real-time via WebSocket, **so that** I know when my uploaded documents are ready for investigation.

**Acceptance Criteria:**
1. `WS /ws/pipeline` accepts a WebSocket connection.
2. Pipeline events (documents.parsed, documents.chunked, entities.extracted, graph.updated, kb.ready) are forwarded to connected clients scoped by `knowledge_base_id`.
3. Clients send `{"subscribe": {"kb_id": "..."}}` to scope updates.
4. Each message includes: `event_type`, `knowledge_base_id`, `progress` (stage name), `timestamp`.
5. Test verifies scoped subscription receives only matching events.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E5-S07 |

**Notes:** Reuse the same WebSocket hub infrastructure from E5-S07. Consider a single `/ws` endpoint with channel-based routing.

---

### E5-S09: Analytics router — risk scores and timeseries

**As an** analyst, **I want** API endpoints for risk scores and timeseries data, **so that** the dashboard can display risk-ranked entities and trend charts.

**Acceptance Criteria:**
1. `api/routers/analytics.py` defines `GET /analytics/risk-scores?kb_id=...&entity_type=...&limit=20` returning `RiskScoreListResponse(items: list[RiskScore])`.
2. `GET /analytics/timeseries?kb_id=...&metric=...&start=...&end=...` returning `TimeseriesResponse(points: list[TimeseriesPoint])`.
3. Both delegate to protocol-based analytics services via DI.
4. Returns 400 if required query params are missing.
5. Tests verify delegation and parameter validation.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E1-S07 |

**Notes:** The analytics service implementations are not yet built — routers should work with mock services for now. Response models live in `analytics/` submodules.

---

### E5-S10: Analytics router — GNN cluster results

**As an** analyst, **I want** an API endpoint for GNN clustering results, **so that** the dashboard can display detected communities and anomalous subgraphs.

**Acceptance Criteria:**
1. `GET /analytics/gnn/clusters?kb_id=...` returns `GnnClusterResponse(clusters: list[ClusterResult])`.
2. Each `ClusterResult` contains: `cluster_id`, `entity_ids`, `anomaly_score`, `label`.
3. Delegates to a GNN analytics service via DI.
4. Returns empty list when GNN capability is disabled in config.
5. Test verifies response shape and empty-when-disabled behavior.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P3 | S | E5-S09 |

**Notes:** GNN analysis is a deferred capability. The router should be ready for when the GNN module is implemented.

---

### E5-S11: Knowledge base router — create and list KBs

**As an** analyst, **I want** to create new knowledge bases and list existing ones via the API, **so that** I can organize document collections for separate investigations.

**Acceptance Criteria:**
1. `POST /knowledgebases` accepts `CreateKbRequest(name: str, description: str)` and returns the created `KnowledgeBase` with status 201.
2. `GET /knowledgebases` returns `KbListResponse(items: list[KnowledgeBase], total: int)` with `limit`/`offset` pagination.
3. KB creation generates a unique ID and publishes a `KnowledgeBaseCreatedEvent`.
4. Duplicate names are allowed (IDs are unique).
5. Tests verify creation, listing, and pagination.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E1-S09 |

**Notes:** KB metadata needs a persistence layer. For MVP, an in-memory dict in the KB service is acceptable. Production persistence is a future story.

---

### E5-S12: Knowledge base router — get and delete KB

**As an** analyst, **I want** to retrieve a single knowledge base by ID and delete a knowledge base with all associated data, **so that** I can manage the lifecycle of investigations.

**Acceptance Criteria:**
1. `GET /knowledgebases/{kb_id}` returns the `KnowledgeBase` record or 404.
2. `DELETE /knowledgebases/{kb_id}` removes the KB metadata, all stored artifacts (documents, chunks, extractions, graph data, vectors), and returns 204.
3. Delete publishes a `KnowledgeBaseDeletedEvent`.
4. Returns 404 if KB does not exist.
5. Tests cover get, delete, and delete-of-nonexistent.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E5-S11, E3-S08 |

**Notes:** Delete must cascade to object store (via `list_keys` prefix delete) and graph/vector store. The cascade can be synchronous for MVP or event-driven for production.

---

### E5-S13: Knowledge base router — list and delete documents within a KB

**As an** analyst, **I want** to list documents in a knowledge base and delete individual documents, **so that** I can manage ingested content granularly.

**Acceptance Criteria:**
1. `GET /knowledgebases/{kb_id}/documents` returns `DocumentListResponse(items: list[DocumentSummary], total: int)` with pagination.
2. `DocumentSummary` includes: `id`, `filename`, `content_type`, `size_bytes`, `status`, `created_at`.
3. `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` removes the document and its derived artifacts, returns 204.
4. Returns 404 if KB or document does not exist.
5. Tests verify listing and deletion.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E5-S11 |

**Notes:** Document metadata must be stored at registration time (currently only the event payload tracks it). An in-memory document registry in the KB service is sufficient for MVP.

---

### E5-S14: Register all new routers in the app factory

**As a** platform developer, **I want** all new routers (alerts, investigation, chat, ws, analytics, updated knowledgebases) registered in `api/app.py`, **so that** the API gateway exposes the complete endpoint surface.

**Acceptance Criteria:**
1. `api/app.py` includes all routers: alerts, investigation, chat, ws, analytics, knowledgebases.
2. Each router is mounted under a consistent prefix (`/alerts`, `/investigation`, `/chat`, `/ws`, `/analytics`, `/knowledgebases`).
3. `GET /health` still works.
4. An integration test starts the app and verifies all expected route prefixes are registered.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | XS | E5-S01, E5-S03, E5-S05, E5-S07, E5-S09, E5-S11 |

**Notes:** This is a wiring-only story. Each router is independently testable — this story just brings them together.

---

## Epic 6: RAG Pipeline

> Wire the RAG service's four adapter slots to production implementations, add streaming support and citation formatting, make the system prompt configurable from domain config, and achieve ≥ 85 % test coverage.

### E6-S01: Production QueryEmbedder adapter — delegate to EmbeddingsService

**As a** platform developer, **I want** a `ServiceQueryEmbedder` adapter that delegates `embed_query` to the `EmbeddingsService`, **so that** RAG queries use the same embedding model as the ingestion pipeline.

**Acceptance Criteria:**
1. `rag/adapters/embeddings_bridge.py` implements `QueryEmbedderProtocol`.
2. The adapter accepts an `EmbeddingsServiceProtocol` dependency and calls `embed_batch` with a single-item list, returning the resulting vector.
3. A unit test confirms the adapter forwards the call and returns the correct vector.
4. The adapter raises `RagConfigurationError` if the embeddings service returns an empty result.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E3-S04 |

**Notes:** E3-S04 delivers the sentence-transformers embeddings adapter. This story bridges the RAG module to it without introducing a direct import — only the protocol is used.

---

### E6-S02: Production ContextRetriever adapter — delegate to VectorStoreService

**As a** platform developer, **I want** a `ServiceContextRetriever` adapter that delegates `retrieve` to the `VectorStoreService`, **so that** RAG retrieval queries the production vector index.

**Acceptance Criteria:**
1. `rag/adapters/vectorstore_bridge.py` implements `ContextRetrieverProtocol`.
2. The adapter accepts a `VectorStoreServiceProtocol` dependency, converts the query vector and filters into a `VectorSearchRequest`, and maps results to `RetrievedContextItem` list.
3. A unit test with a mock vectorstore service verifies mapping correctness, including score passthrough and metadata preservation.
4. Returns an empty list (not an error) when zero results are found.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E3-S02 |

**Notes:** E3-S02 delivers the Qdrant adapter. This adapter translates between the RAG and vectorstore module contracts.

---

### E6-S03: Production GraphContextExpander adapter — delegate to GraphService

**As a** platform developer, **I want** a `ServiceGraphContextExpander` adapter that delegates `expand` to the `GraphService`, **so that** RAG answers include graph-neighborhood context around retrieved entities.

**Acceptance Criteria:**
1. `rag/adapters/graph_bridge.py` implements `GraphContextExpanderProtocol`.
2. The adapter accepts a `GraphServiceProtocol` dependency, extracts entity IDs from `context_items`, calls `get_neighbors` per entity (depth configurable, default 1), and assembles a `GraphContext`.
3. A unit test verifies correct graph traversal delegation and `GraphContext` assembly.
4. If the graph service returns no neighbors, the adapter returns a `GraphContext` with an empty summary — no error.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E2-S01, E2-S02 |

**Notes:** Expansion depth should come from `RagConfig.expansion_depth` in domain config (E1-S06). Graceful degradation: if expansion fails, log and continue without graph context.

---

### E6-S04: Production AnswerGenerator adapter — delegate to LLMService

**As a** platform developer, **I want** a `ServiceAnswerGenerator` adapter that delegates `generate` to the `LLMService`, **so that** RAG answers are produced by the configured LLM provider.

**Acceptance Criteria:**
1. `rag/adapters/llm_bridge.py` implements `AnswerGeneratorProtocol`.
2. The adapter accepts an `LlmServiceProtocol` dependency, assembles a prompt from the `RagGenerationRequest` (system prompt + context + question), and maps the LLM response to `RagGenerationResult`.
3. A unit test with a mock LLM service verifies prompt assembly and result mapping.
4. Token budget enforcement: the adapter truncates context items if total token estimate exceeds `LlmConfig.max_tokens * 0.8`.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E3-S05 |

**Notes:** E3-S05 delivers the OpenAI LLM adapter. Prompt template assembly should be extracted into a testable helper to allow domain-specific prompt strategies.

---

### E6-S05: Domain-configurable RAG system prompt

**As a** platform operator, **I want** the RAG system prompt to be loaded from `RagConfig.system_prompt_template` in domain config, **so that** the same platform serves different analytical domains without code changes.

**Acceptance Criteria:**
1. `RagService.answer()` reads `system_prompt` from the request and falls back to `RagConfig.system_prompt_template` from domain config when the request field is `None`.
2. The system prompt template supports `{domain_name}` and `{entity_types}` placeholders, resolved at call time from `DomainConfig`.
3. A unit test verifies placeholder resolution and fallback behavior.
4. The default YAML fixture includes a sample system prompt template.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E1-S06 |

**Notes:** The prompt template is intentionally simple string formatting — not a Jinja engine. Keep it minimal and add complexity only when domains require it.

---

### E6-S06: Streaming RAG response support

**As a** platform developer, **I want** `RagService` to support streaming answer generation via an iterator-based protocol method, **so that** the frontend can display partial answers as they arrive.

**Acceptance Criteria:**
1. `AnswerGeneratorProtocol` gains a `stream_generate(request: RagGenerationRequest) -> Iterator[str]` method.
2. `RagServiceProtocol` gains a `stream_answer(request: RagQueryRequest) -> Iterator[RagStreamChunk]` method.
3. `RagStreamChunk` model contains `chunk_text: str`, `is_final: bool`, and optional `citations: list[RagCitation]` (only on final chunk).
4. `InMemoryAnswerGenerator` implements `stream_generate` by yielding the full answer in one chunk.
5. `RagService.stream_answer()` embeds the query, retrieves context, then delegates to `stream_generate` and wraps each yielded string in a `RagStreamChunk`.
6. A unit test verifies the streaming pipeline end-to-end with the in-memory adapter.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E6-S04 |

**Notes:** The API layer (E5-S05) will expose this via SSE or WebSocket. This story handles only the service-layer streaming contract.

---

### E6-S07: Citation formatting with source references

**As an** analyst, **I want** RAG responses to include structured citations linking answer claims to specific source documents and chunk offsets, **so that** I can verify the evidence behind each answer.

**Acceptance Criteria:**
1. `RagCitation` is extended with `document_id: str | None`, `chunk_index: int | None`, and `highlight: str | None` fields.
2. The citation builder in `RagService` maps `RetrievedContextItem.metadata` fields (`document_id`, `chunk_index`) to citation fields when available.
3. A unit test verifies citation field population when metadata is present and graceful `None` when absent.
4. The `RagQueryResponse.citations` list is ordered by descending relevance score.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | None |

**Notes:** Citation highlight extraction (substring of the source chunk that best supports the answer) is deferred — populate `highlight` with the existing `snippet` for now.

---

### E6-S08: RAG module test suite — achieve ≥ 85 % coverage

**As a** platform developer, **I want** comprehensive pytest coverage for the RAG module, **so that** the service, adapters, models, and error paths are validated before production deployment.

**Acceptance Criteria:**
1. `pytest --cov=rag tests/rag/` reports ≥ 85 % line coverage.
2. Tests cover: happy-path `answer()`, retrieval failure → `RagRetrievalError`, generation failure → `RagGenerationError`, configuration error paths, empty context list, graph expansion disabled (no expander), graph expansion failure with graceful degradation.
3. Tests cover each production bridge adapter (E6-S01 through E6-S04) with mocked downstream services.
4. Tests cover streaming `stream_answer()` happy path and partial failure.
5. All tests are isolated — no network, no external models.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E6-S01, E6-S02, E6-S03, E6-S04, E6-S06 |

**Notes:** Existing test files in `tests/rag/` have some content but the coverage is reported as minimal. Expand and fill gaps.

---

## Epic 7: Analytics Suite

> Upgrade the four analytics sub-modules from basic heuristics to production-quality algorithms, wire analytics into the coordinator event chain, and implement the self-reinforcing analysis loop that writes scores back to the graph.

### E7-S01: Timeseries — seasonal decomposition anomaly detection

**As a** platform developer, **I want** the timeseries service to support STL seasonal decomposition alongside z-score detection, **so that** anomaly detection accounts for seasonal patterns in time-series data.

**Acceptance Criteria:**
1. `TimeseriesService` accepts a `detection_strategy: Literal["z_score", "stl_decomposition"]` parameter (configurable via `TimeseriesAnalysisRequest` with default `"z_score"`).
2. A new `_detect_anomalies_stl()` function decomposes the series into trend, seasonal, and residual components and flags residuals beyond the z-threshold.
3. Tests verify that seasonal data produces fewer false positives under STL than under raw z-score.
4. The existing z-score path is unchanged.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | None |

**Notes:** Use `statsmodels.tsa.seasonal.seasonal_decompose` or a pure-Python STL implementation. Add `statsmodels` to `pyproject.toml` optional dependencies under `[analytics]`.

---

### E7-S02: Timeseries — isolation forest anomaly detection

**As a** platform developer, **I want** the timeseries service to support isolation forest anomaly detection, **so that** multi-feature anomaly detection can catch non-distributional outliers.

**Acceptance Criteria:**
1. A new `detection_strategy: Literal[..., "isolation_forest"]` option is added to `TimeseriesAnalysisRequest`.
2. A new `_detect_anomalies_isolation_forest()` function trains a single-feature isolation forest on the observation values and flags anomalies.
3. Tests verify detection on synthetic data with planted outliers.
4. The contamination parameter is configurable via the request (default `0.05`).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | None |

**Notes:** Use `scikit-learn` `IsolationForest`. Add to optional dependencies. Keep the interface identical to other strategies — return `list[AnomalyPoint]`.

---

### E7-S03: Timeseries — sliding window continuous analysis

**As a** platform developer, **I want** the timeseries service to support sliding-window analysis over the most recent N observations, **so that** continuous monitoring detects anomalies in real-time streams without reprocessing full history.

**Acceptance Criteria:**
1. `TimeseriesAnalysisRequest` gains a `window_size: int | None = None` field.
2. When `window_size` is set, only the last `window_size` observations are analyzed (baseline is derived from the window).
3. Tests verify window truncation and that results differ from full-history analysis on the same series.
4. Window size zero or negative raises `TimeseriesConfigurationError`.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | None |

**Notes:** This enables the monitoring module to call timeseries analysis on rolling windows from the stream consumer.

---

### E7-S04: GNN — community detection (Louvain)

**As a** platform developer, **I want** the GNN service to detect communities in the graph snapshot, **so that** analysts can identify clusters of related entities (e.g., coordinated fraud rings).

**Acceptance Criteria:**
1. `GnnAnalysisResponse` gains a `communities: list[GnnCommunity]` field, where `GnnCommunity` contains `community_id: str`, `member_entity_ids: list[str]`, `density: float`.
2. The `GnnService.analyze()` method runs community detection after node scoring.
3. Each `GnnNodeScore.cluster_id` is set to the detected community ID instead of the current placeholder.
4. Tests verify community detection on a graph with two clearly separated clusters.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | None |

**Notes:** Use `networkx` community detection (Louvain via `community_louvain` or `networkx.algorithms.community`). Add `networkx` to dependencies if not already present. Keep the pure-Python path for testing; a future story can add GPU-accelerated community detection.

---

### E7-S05: GNN — node embedding export

**As a** platform developer, **I want** the GNN service to produce node embeddings for each entity in the graph snapshot, **so that** downstream modules (vectorstore, risk) can leverage structural similarity.

**Acceptance Criteria:**
1. `GnnAnalysisResult` gains `node_embeddings: dict[str, list[float]]` mapping entity IDs to embedding vectors.
2. `GnnService.analyze()` computes node embeddings using a configurable method (default: `"node2vec"` or `"spectral"`).
3. Embeddings are normalized to unit length.
4. Tests verify embedding dimensionality and normalization on a small graph.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P3 | L | E7-S04 |

**Notes:** Use `networkx` spectral embedding or `node2vec` (from `node2vec` PyPI package). This is a nice-to-have that enables "write embeddings back to vectorstore" in the self-reinforcing loop.

---

### E7-S06: Risk scoring — ensemble model with configurable strategies

**As a** platform developer, **I want** the risk service to support pluggable scoring strategies (linear, logistic, gradient boosting) behind a `RiskScoringStrategy` protocol, **so that** risk assessment quality can improve without modifying the service core.

**Acceptance Criteria:**
1. `analytics/risk/protocols.py` defines `RiskScoringStrategyProtocol` with `score(signals: list[RiskSignal]) -> list[RiskFactor]`.
2. The existing linear weighted-sum logic is extracted into `LinearScoringStrategy` implementing the protocol.
3. `RiskService` accepts a `scoring_strategy: RiskScoringStrategyProtocol` dependency.
4. Tests verify the service delegates to the injected strategy and that `LinearScoringStrategy` produces identical results to the current inline implementation.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | None |

**Notes:** This is a structural refactor that enables E7-S07. No ML model training is included — just the pluggable interface and the extraction of existing logic.

---

### E7-S07: Risk scoring — temporal trend comparison

**As a** platform developer, **I want** the risk service to compare the current assessment score to a historical baseline, **so that** risk reports indicate whether an entity's risk is increasing, stable, or decreasing.

**Acceptance Criteria:**
1. `RiskAssessmentResponse` gains `trend: Literal["increasing", "stable", "decreasing"] | None` and `previous_score: float | None`.
2. `RiskSignalSourceProtocol` gains `load_historical_score(knowledge_base_id, entity_id) -> float | None`.
3. `RiskService.assess()` fetches the historical score (if available) and computes trend using a configurable delta threshold (default `0.05`).
4. `InMemoryRiskSignalSource` implements the new method, returning `None` by default.
5. Tests verify trend calculation for each trend outcome.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E7-S06 |

**Notes:** Historical score persistence is the responsibility of the self-reinforcing loop (E7-S11). Until then, the in-memory adapter returns `None` and trend is `None`.

---

### E7-S08: Explainability — structured narrative generation

**As a** platform developer, **I want** the explainability service to produce structured multi-section narratives instead of concatenated strings, **so that** the investigation workbench can render formatted evidence reports.

**Acceptance Criteria:**
1. `ExplainabilityResponse` gains a `narrative: ExplanationNarrative` field with `summary: str`, `sections: list[NarrativeSection]`.
2. `NarrativeSection` contains `heading: str`, `body: str`, `evidence_refs: list[str]`.
3. `_build_reasoning()` is refactored to produce the structured narrative, grouping explanation items by `source_type`.
4. The existing `evidence_pack.reasoning` field is populated with the flattened `summary` for backward compatibility.
5. Tests verify section grouping and backward-compatible `reasoning` field.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | None |

**Notes:** Full LLM-generated narratives (SHAP/LIME) are a separate P3 follow-up. This story is about structured output, not AI-generated text.

---

### E7-S09: Explainability — SHAP/LIME feature attribution adapter

**As a** platform developer, **I want** an explainability adapter that uses SHAP or LIME to attribute risk scores to specific features, **so that** analysts understand which input features drive risk assessment outcomes.

**Acceptance Criteria:**
1. `analytics/explainability/adapters/shap_adapter.py` implements `ExplainabilityContextSourceProtocol`.
2. The adapter accepts a trained model artifact (path or callable) and input feature matrix, computes SHAP values, and maps them to `ExplanationItem` instances.
3. A test with a minimal `sklearn` model verifies SHAP value computation and mapping.
4. The adapter is optional — importable only when `shap` is installed (guarded import).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P3 | L | E7-S06 |

**Notes:** Add `shap` to `pyproject.toml` optional dependencies under `[analytics]`. This adapter is opt-in and not required for the base platform.

---

### E7-S10: Wire analytics into the coordinator event chain

**As a** platform developer, **I want** the worker coordinator to consume `graph.updated` events and trigger the analytics pipeline (timeseries → GNN → risk → explainability), **so that** knowledge base updates automatically produce risk assessments and evidence packs.

**Acceptance Criteria:**
1. `agent/coordinator.py` gains a `handle_graph_updated()` handler that triggers `GnnService.analyze()`, `RiskService.assess()` (for top-scored entities), and `ExplainabilityService.generate()` (for entities above the risk threshold).
2. `build_worker_dependencies()` instantiates analytics services alongside ingestion services.
3. The coordinator subscribes to `graph.updated` and dispatches to the analytics handler.
4. An integration test verifies the full chain: `graph.updated` → GNN analysis → risk assessment → explainability → `alerts.created`.
5. Analytics failures are logged and do not block the pipeline — errors produce `analysis.failed` events.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | L | E7-S06, E1-S07 |

**Notes:** Timeseries analysis requires historical observation data that may not be available immediately after `graph.updated`. Wire timeseries as an optional stage — skip if the entity has no time-series history.

---

### E7-S11: Self-reinforcing loop — write risk scores back to graph

**As a** platform developer, **I want** the coordinator to write computed risk scores and GNN community labels back to graph entity properties after analytics complete, **so that** subsequent queries and visualizations reflect the latest analysis.

**Acceptance Criteria:**
1. After `RiskService.assess()` completes, the coordinator calls `GraphService.update_entity_properties()` to set `risk_score`, `risk_level`, and `risk_assessed_at` on the entity.
2. After `GnnService.analyze()` completes, the coordinator sets `community_id` and `centrality_score` on each scored entity.
3. Property writes are idempotent — repeated runs overwrite previous scores.
4. Tests verify property persistence on the in-memory graph adapter.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E7-S10, E2-S01 |

**Notes:** `GraphService` may need a lightweight `update_entity_properties(kb_id, entity_id, properties: dict)` method. Check if the existing `upsert_entities` covers this use case before adding a new method.

---

### E7-S12: Analytics module test coverage — achieve ≥ 85 % per sub-module

**As a** platform developer, **I want** comprehensive pytest coverage for all four analytics sub-modules, **so that** algorithm correctness is validated before production deployment.

**Acceptance Criteria:**
1. `pytest --cov=analytics tests/analytics/` reports ≥ 85 % line coverage for each of `timeseries/`, `gnn/`, `risk/`, `explainability/`.
2. Tests cover: happy-path analysis, insufficient-data error paths, configuration errors, each detection strategy (z-score, STL, isolation forest), community detection, streaming scoring, structured narrative generation.
3. Tests are deterministic with seeded random state where applicable.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E7-S01, E7-S02, E7-S04, E7-S06, E7-S08 |

**Notes:** Existing tests in `tests/analytics/` cover basic paths. Expand to cover new strategies and edge cases. Use `pytest-cov` per-package reporting.

---

## Epic 8: Monitoring & Alerting

> Upgrade the monitoring service from simple threshold evaluation to production-quality alerting with deduplication, suppression, alert lifecycle management, and a continuous stream consumer.

### E8-S01: Time-window aggregation for monitoring evaluation

**As a** platform developer, **I want** the monitoring service to evaluate observations within configurable time windows, **so that** transient spikes are distinguished from sustained anomalies.

**Acceptance Criteria:**
1. `MonitoringEvaluationRequest` gains `window_minutes: int = 60` and `min_observations_in_window: int = 1`.
2. The evaluation logic filters observations to those within the time window before applying thresholds.
3. An alert is generated only if `min_observations_in_window` observations exceed the threshold within the window.
4. Tests verify windowed filtering with observations at various timestamps.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** `MonitoringObservation.observed_at` is already a datetime field. The window filter is applied before the existing threshold evaluation.

---

### E8-S02: Alert deduplication within configurable window

**As a** platform developer, **I want** the monitoring service to suppress duplicate alerts for the same entity and metric within a configurable deduplication window, **so that** analysts are not overwhelmed by repeated alerts for the same condition.

**Acceptance Criteria:**
1. `MonitoringService` maintains a deduplication index keyed by `(entity_id, metric_name)` with last-alert timestamps.
2. `MonitoringConfig.dedup_window_seconds` (default 3600) controls the suppression interval.
3. If an alert for the same key was created within the window, the duplicate is suppressed and counted in the response as `suppressed_count`.
4. `MonitoringEvaluationResponse` gains `suppressed_count: int = 0`.
5. Tests verify deduplication across two evaluation calls within and outside the window.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E1-S06 |

**Notes:** The deduplication index should be injectable (protocol) to allow Redis-backed dedup in production. Start with an in-memory dict for the default adapter.

---

### E8-S03: Alert suppression rules and maintenance windows

**As a** platform operator, **I want** to define suppression rules (entity type, metric name, time range) that prevent alert generation during planned maintenance, **so that** known maintenance windows do not produce false-positive alerts.

**Acceptance Criteria:**
1. `monitoring/models.py` defines `SuppressionRule` with `entity_type: str | None`, `metric_name: str | None`, `start_time: datetime`, `end_time: datetime`, `reason: str`.
2. `MonitoringService` accepts a `suppression_rules: list[SuppressionRule]` parameter (injectable, default empty).
3. Observations matching an active suppression rule are excluded from threshold evaluation.
4. `MonitoringEvaluationResponse` gains `suppressed_by_rule_count: int = 0`.
5. Tests verify suppression matching by entity type, metric name, and time range.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E8-S02 |

**Notes:** Suppression rules will be managed via the config editor (E9-S09) in the UI. For now, they are injected at service construction time.

---

### E8-S04: Alert rate limiting

**As a** platform developer, **I want** the monitoring service to enforce a maximum alert rate per knowledge base, **so that** alert storms from large batch evaluations do not overwhelm downstream consumers.

**Acceptance Criteria:**
1. `MonitoringConfig` gains `max_alerts_per_evaluation: int = 100`.
2. When the threshold is reached, remaining candidates are logged as `rate_limited_count` in the response but not surfaced as alerts.
3. The highest-severity candidates are prioritized — low-severity alerts are dropped first.
4. `MonitoringEvaluationResponse` gains `rate_limited_count: int = 0`.
5. Tests verify rate limiting with a batch that exceeds the limit.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E1-S06 |

**Notes:** Rate limiting is per-evaluation-call, not global. Global rate limiting across the stream is a future concern.

---

### E8-S05: Alert lifecycle state machine

**As a** platform developer, **I want** `Alert` to implement a state machine with transitions `open → acknowledged → investigating → resolved → dismissed`, **so that** alert management follows a consistent lifecycle with audit-safe transitions.

**Acceptance Criteria:**
1. `shared/types.py` `Alert.status` is typed as `Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]` (this may already exist from E1-S10; confirm and extend if needed).
2. A `transition_alert_status(alert, new_status, actor: str) -> Alert` function enforces valid transitions and updates `updated_at`, `resolved_by` (on resolve), and `resolution_notes`.
3. Invalid transitions raise `AlertLifecycleError`.
4. Valid transitions: open→acknowledged, open→dismissed, acknowledged→investigating, investigating→resolved, investigating→dismissed, any→open (reopen).
5. Tests verify each valid transition and at least two invalid transitions.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E1-S10 |

**Notes:** This function lives in `monitoring/service.py` or a new `monitoring/lifecycle.py`. It operates on the shared `Alert` type — no new model needed.

---

### E8-S06: Alert grouping and correlation

**As a** platform developer, **I want** the monitoring service to group related alerts (same entity type, similar time, connected in graph) into alert groups, **so that** analysts can investigate correlated events together.

**Acceptance Criteria:**
1. `monitoring/models.py` defines `AlertGroup` with `group_id: str`, `alert_ids: list[str]`, `entity_type: str`, `created_at: datetime`, `correlation_reason: str`.
2. After alert generation, the monitoring service runs a grouping pass that clusters alerts sharing an entity type and generated within a configurable time tolerance (default 300 seconds).
3. `MonitoringEvaluationResponse` gains `alert_groups: list[AlertGroup] = Field(default_factory=list)`.
4. Tests verify grouping of related alerts and non-grouping of dissimilar alerts.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E8-S05 |

**Notes:** Graph-based correlation (alerts on entities connected in the graph) is a P3 follow-up. This story covers time + entity-type correlation only.

---

### E8-S07: Monitoring stream consumer — continuous evaluation

**As a** platform developer, **I want** the worker coordinator to consume `graph.updated` and `analysis.complete` events and trigger continuous monitoring evaluation, **so that** new entities and updated risk scores are automatically monitored.

**Acceptance Criteria:**
1. `agent/coordinator.py` gains a `handle_analysis_complete()` handler that creates a `MonitoringEvaluationRequest` from the analysis results and calls `MonitoringService.evaluate()`.
2. The coordinator subscribes to `risk.scored` events (published by the risk service) as the analysis-completion trigger.
3. `build_worker_dependencies()` instantiates `MonitoringService` with the configured observation source.
4. An integration test verifies: `risk.scored` → monitoring evaluation → `alerts.created`.
5. Monitoring failures are logged but do not block the pipeline.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E7-S10, E8-S01 |

**Notes:** The observation source requires risk scores to already be computed. This positions monitoring at the tail of the analytics chain: graph.updated → analytics → risk.scored → monitoring → alerts.created.

---

### E8-S08: Monitoring module test suite — achieve ≥ 85 % coverage

**As a** platform developer, **I want** comprehensive pytest coverage for the monitoring module, **so that** threshold evaluation, deduplication, suppression, lifecycle, and grouping are validated.

**Acceptance Criteria:**
1. `pytest --cov=monitoring tests/monitoring/` reports ≥ 85 % line coverage.
2. Tests cover: happy-path evaluation, time-window filtering, deduplication, suppression rules, rate limiting, alert lifecycle transitions, alert grouping, stream consumer error paths.
3. Existing tests in `tests/monitoring/` are expanded — not replaced.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E8-S01, E8-S02, E8-S03, E8-S04, E8-S05, E8-S06 |

**Notes:** Current test files have minimal content. Fill all gaps introduced by E8-S01 through E8-S07.

---

## Epic 9: Frontend Application

> Build the chiliAI React frontend from scaffold to functional application: app shell, routing, state management, API integration, and all six application pages.

### E9-S01: App shell, routing, and layout scaffold

**As a** frontend developer, **I want** a top-level app shell with sidebar navigation, route definitions for all six pages, and a responsive layout, **so that** page development can proceed in parallel on a stable navigation skeleton.

**Acceptance Criteria:**
1. React Router v7 is installed and configured with routes: `/` (Dashboard), `/knowledgebases` (KB Manager), `/alerts` (Alert Feed), `/investigation` (Investigation Workbench), `/chat` (RAG Chat), `/config` (Configuration).
2. A persistent sidebar component renders navigation links with active-state highlighting.
3. A 404 catch-all route displays a "Not Found" page.
4. The layout is responsive — sidebar collapses to a hamburger menu on mobile viewports.
5. The Vite template placeholder content in `App.tsx` is replaced.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | None |

**Notes:** Install `react-router` v7. Use CSS modules or Tailwind (defer styling library decision to this story). The shell is a container — pages render inside an `<Outlet />`.

---

### E9-S02: Domain config fetching and context provider

**As a** frontend developer, **I want** the app to fetch domain configuration from the API at startup and provide it via React context, **so that** all pages can render domain-specific labels, entity types, and feature gates.

**Acceptance Criteria:**
1. A `useDomainConfig()` hook fetches `GET /config` on mount and provides the parsed config to children via `DomainConfigContext`.
2. The app shell shows a loading spinner while config is fetching and an error boundary if the fetch fails.
3. TypeScript types for `DomainConfig` match the backend `config/schema.py` structure.
4. A mock provider exists for component tests.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E5-S09 |

**Notes:** E5-S09 delivers the config API router. This story consumes it. The config is fetched once and cached — no polling.

---

### E9-S03: TanStack Query integration and API client setup

**As a** frontend developer, **I want** TanStack Query configured as the server-state library with a typed API client generated from the OpenAPI spec, **so that** all API interactions are type-safe, cached, and deduplicated.

**Acceptance Criteria:**
1. `@tanstack/react-query` is installed and a `QueryClientProvider` wraps the app.
2. An OpenAPI codegen step (e.g., `openapi-typescript-codegen` or `orval`) generates typed API client functions from the backend OpenAPI schema.
3. A `package.json` script `codegen:api` runs the generation.
4. A sample query hook (`useKnowledgeBases()`) demonstrates the pattern.
5. Query defaults: stale time 30s, retry 1, refetch on window focus enabled.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E5-S14 |

**Notes:** The backend must be running to export the OpenAPI schema (`GET /openapi.json`). Add a checked-in schema snapshot for offline development.

---

### E9-S04: Zustand client state setup

**As a** frontend developer, **I want** Zustand configured for client-side state (sidebar state, selected entity, active filters), **so that** UI state persists across route changes without prop drilling.

**Acceptance Criteria:**
1. `zustand` is installed.
2. A `useAppStore` store manages: `sidebarOpen: boolean`, `selectedEntityId: string | null`, `activeKnowledgeBaseId: string | null`.
3. Store actions: `toggleSidebar()`, `selectEntity(id)`, `setActiveKnowledgeBase(id)`.
4. A unit test verifies store actions and state transitions.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** Keep the store minimal. Domain-specific state slices are added per-page in follow-up stories. Avoid duplicating server state — TanStack Query handles that.

---

### E9-S05: Dashboard page

**As an** analyst, **I want** a Dashboard page displaying key metrics (entity count, alert count, KB status, recent activity), **so that** I have an at-a-glance overview when I open the application.

**Acceptance Criteria:**
1. `src/pages/Dashboard.tsx` renders KPI cards: total entities, total relationships, open alerts, active knowledge bases.
2. A recent-activity timeline shows the last 10 events (document uploads, alerts, analyses).
3. Data is fetched via TanStack Query hooks calling the analytics and KB endpoints.
4. Cards show loading skeletons while fetching.
5. The page is the default route (`/`).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E9-S03, E5-S09 |

**Notes:** Design is functional — not pixel-perfect. Use a simple grid layout. Metrics endpoints may not exist yet; wire to mocked data and replace when backend endpoints land.

---

### E9-S06: Knowledge Base Manager page — list and create

**As an** analyst, **I want** a Knowledge Base Manager page where I can view existing knowledge bases and create new ones, **so that** I can manage the data sources for my investigations.

**Acceptance Criteria:**
1. `src/pages/KnowledgeBaseManager.tsx` renders a table of knowledge bases with columns: name, status, document count, created date.
2. A "Create Knowledge Base" button opens a form dialog with name and description fields.
3. Form submission calls `POST /knowledgebases` and invalidates the list query on success.
4. Inline status badges show KB lifecycle state (active, building, ready, error).
5. Error states (API failure) display a toast notification.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E9-S03, E5-S11 |

**Notes:** E5-S11 delivers the knowledgebases router. Use `useMutation` for create, `useQuery` for list.

---

### E9-S07: Knowledge Base Manager — document upload and delete

**As an** analyst, **I want** to upload documents to a knowledge base and delete individual documents, **so that** I can manage the content feeding my investigations.

**Acceptance Criteria:**
1. KB detail view shows a document table with columns: filename, content type, size, status, uploaded date.
2. A drag-and-drop upload zone accepts files (TXT, JSON, CSV, XLSX, PDF, DOCX) up to 50 MB.
3. Upload calls `POST /knowledgebases/{kb_id}/documents` with multipart form data.
4. A progress indicator shows upload status.
5. Delete button per document calls `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` with confirmation dialog.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E9-S06, E5-S13 |

**Notes:** File type validation is client-side (allow list). Size constraint is enforced client-side and server-side.

---

### E9-S08: Alert Feed page

**As an** analyst, **I want** an Alert Feed page that lists alerts with filtering and bulk acknowledgment, **so that** I can triage suspicious activities efficiently.

**Acceptance Criteria:**
1. `src/pages/AlertFeed.tsx` renders a sortable, filterable table of alerts.
2. Filters: severity (multi-select), status (multi-select), entity type, date range.
3. Bulk actions: acknowledge selected, dismiss selected.
4. Clicking an alert navigates to the Investigation Workbench with the alert's entity pre-selected.
5. Real-time updates via WebSocket push new alerts to the top of the feed.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E9-S03, E5-S01, E9-S12 |

**Notes:** E5-S01 delivers the alerts router. E9-S12 delivers the WebSocket hook for real-time updates.

---

### E9-S09: Configuration Editor page

**As a** platform operator, **I want** a Configuration Editor page that displays and edits the domain configuration YAML, **so that** I can tune entity types, relationship types, thresholds, and system prompts without redeploying.

**Acceptance Criteria:**
1. `src/pages/ConfigEditor.tsx` fetches the current config and renders it in a code editor component (e.g., Monaco or CodeMirror).
2. Syntax highlighting for YAML.
3. A "Save" button calls `PUT /config` and shows success/failure feedback.
4. A "Reset to defaults" button restores the default config from the server.
5. Validation errors from the backend are displayed inline.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E9-S02, E5-S09 |

**Notes:** The config API router (E5-S09) must support PUT. If it currently only supports GET, coordinate with that story. Consider a diff view before save.

---

### E9-S10: Investigation Workbench — graph visualization

**As an** analyst, **I want** an Investigation Workbench page with an interactive graph visualization, **so that** I can visually explore entity relationships and identify suspicious patterns.

**Acceptance Criteria:**
1. `src/pages/InvestigationWorkbench.tsx` renders a force-directed graph using a WebGL-capable library (e.g., `react-force-graph`, `sigma.js`, or `cytoscape.js`).
2. Nodes are color-coded by entity type, sized by risk score.
3. Edges display relationship type on hover.
4. Click a node to select it (updates `selectedEntityId` in Zustand store).
5. Zoom, pan, and drag are supported.
6. Graph data is fetched from `GET /investigation/subgraph/{entity_id}`.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E9-S04, E5-S03 |

**Notes:** E5-S03 delivers the investigation router. Start with a 2D force-directed layout. 3D is a future enhancement. Performance: lazy-load the graph library.

---

### E9-S11: Investigation Workbench — entity detail and evidence panels

**As an** analyst, **I want** side panels showing entity details and evidence packs when I select a node in the graph, **so that** I can review supporting data without leaving the visualization.

**Acceptance Criteria:**
1. Selecting a node in the graph opens an Entity Detail panel showing: entity type, all properties, risk score, community ID, timestamps.
2. Below entity details, an Evidence Panel lists related evidence packs with reasoning summaries and confidence scores.
3. Each evidence item is expandable to show full quotes and source document references.
4. A timeline view shows entity-related events in chronological order.
5. Panels are collapsible and do not obscure the graph.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E9-S10, E5-S03 |

**Notes:** Entity detail and evidence data come from the investigation endpoints. Use a split-pane layout (graph left, panels right).

---

### E9-S12: WebSocket hook for real-time updates

**As a** frontend developer, **I want** a `useWebSocket()` hook that connects to the backend WebSocket endpoint and dispatches real-time events to the UI, **so that** pages like Alert Feed and Dashboard update without polling.

**Acceptance Criteria:**
1. `src/hooks/useWebSocket.ts` connects to `ws://<host>/ws` and auto-reconnects on disconnect (exponential backoff, max 5 retries).
2. The hook parses incoming JSON messages and dispatches typed events via a callback.
3. Supported event types: `alert.created`, `analysis.complete`, `document.processed`.
4. A connection-status indicator component shows connected/disconnected/reconnecting state.
5. Tests verify reconnection logic with a mock WebSocket server.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E5-S07 |

**Notes:** E5-S07 delivers the backend WebSocket endpoint. Use the native `WebSocket` API — no additional library needed.

---

### E9-S13: RAG Chat page

**As an** analyst, **I want** a RAG Chat page where I can ask questions about a knowledge base and receive answers with citations, **so that** I can investigate entities conversationally.

**Acceptance Criteria:**
1. `src/pages/RagChat.tsx` renders a chat interface with a message input and response display area.
2. KB selector dropdown lets the user choose the active knowledge base context.
3. Submitting a question calls the RAG chat endpoint and displays the streaming response.
4. Citations are rendered as clickable links that navigate to the source document or entity in the Investigation Workbench.
5. Conversation history is maintained in client state for the session.
6. A loading indicator shows while the response is generating.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E9-S03, E5-S05, E6-S06 |

**Notes:** E5-S05 delivers the chat router. E6-S06 delivers streaming support. Use SSE for streaming responses. Markdown rendering for answer text.

---

## Epic 10: Quality, Security & Operations

> Establish CI/CD, close test coverage gaps, add authentication, observability, security hardening, and production deployment infrastructure.

### E10-S01: GitHub Actions CI pipeline — lint, typecheck, test, build

**As a** platform developer, **I want** a GitHub Actions workflow that lints, typechecks, tests, and builds both backend and frontend on every PR, **so that** quality regressions are caught before merge.

**Acceptance Criteria:**
1. `.github/workflows/ci.yml` defines a workflow triggered on push to `main` and all PRs.
2. Backend jobs: `ruff check`, `pyright --strict`, `pytest --cov` with coverage threshold enforcement (fail if any package < 85 %).
3. Frontend jobs: `npm run lint`, `npm run build` (includes `tsc -b`).
4. Jobs run in parallel (backend and frontend are independent).
5. Coverage reports are uploaded as artifacts.
6. Workflow uses caching for `pip` and `npm` dependencies.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | None |

**Notes:** Use `ubuntu-latest` runner. Python 3.12, Node 22. Add a `.python-version` file at repo root if not present. The Makefile can be used for local parity.

---

### E10-S02: Backend test coverage gap closure — LLM module

**As a** platform developer, **I want** ≥ 85 % test coverage for the `llm/` module, **so that** the LLM service, adapters, and error paths are validated.

**Acceptance Criteria:**
1. `pytest --cov=llm tests/llm/` reports ≥ 85 % line coverage.
2. Tests cover: happy-path completion, provider error → `LlmProviderError`, configuration error paths, token limit handling, in-memory adapter behavior.
3. Tests are isolated — no API calls to real LLM providers.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** Existing test files in `tests/llm/` have some content. Review and expand to reach the coverage target.

---

### E10-S03: Backend test coverage gap closure — config module

**As a** platform developer, **I want** ≥ 85 % test coverage for the `config/` module, **so that** configuration loading, validation, and defaults are fully tested.

**Acceptance Criteria:**
1. `pytest --cov=config tests/config/` reports ≥ 85 % line coverage.
2. Tests cover: valid config load, missing file fallback, schema validation errors, cross-field validators (e.g., dimensions mismatch), all config section defaults.
3. Tests cover the domain-specific sections added in E1-S04 through E1-S06.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E1-S06 |

**Notes:** Current coverage is ~65 %. Identify uncovered branches with `pytest --cov-report=term-missing`.

---

### E10-S04: Backend test coverage gap closure — graph module

**As a** platform developer, **I want** ≥ 85 % test coverage for the `graph/` module, **so that** graph operations, queries, and error paths are validated.

**Acceptance Criteria:**
1. `pytest --cov=graph tests/graph/` reports ≥ 85 % line coverage.
2. Tests cover: upsert entities, upsert relationships, get_entity, get_neighbors, search_entities, count operations, delete operations, idempotent upserts, error paths.
3. Tests cover the query methods added in E2-S01.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E2-S01 |

**Notes:** Current coverage is ~50 %. The query methods from E2-S01 are the primary gap.

---

### E10-S05: Backend test coverage gap closure — storage module

**As a** platform developer, **I want** ≥ 85 % test coverage for the `storage/` module, **so that** object store operations and adapter behavior are validated.

**Acceptance Criteria:**
1. `pytest --cov=storage tests/storage/` reports ≥ 85 % line coverage.
2. Tests cover: put_bytes, get_bytes, delete, list_keys, key-not-found error, empty content handling, metadata round-trip.
3. Tests cover both in-memory and local-filesystem adapters (if the local adapter exists by this point).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** Current coverage is ~70 %. Add edge-case tests for key collisions and large blob handling.

---

### E10-S06: Auth middleware — JWT/OIDC authentication

**As a** platform operator, **I want** a FastAPI middleware that validates JWT tokens from an OIDC provider, **so that** API endpoints are protected and user identity is available to all handlers.

**Acceptance Criteria:**
1. `api/middleware/auth.py` implements a FastAPI dependency `get_current_user()` that extracts and validates a JWT from the `Authorization: Bearer <token>` header.
2. Token validation includes: signature verification (RS256), expiration check, audience claim, issuer claim.
3. Configuration via `AuthConfig` in domain config: `enabled: bool`, `issuer_url: str`, `audience: str`, `jwks_uri: str`.
4. When `enabled: False`, the middleware returns a default anonymous user — no enforcement.
5. Tests verify: valid token → user identity, expired token → 401, invalid signature → 401, missing header → 401, auth disabled → anonymous.
6. No hardcoded secrets — JWKS fetched from provider.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | L | E1-S06 |

**Notes:** Use `python-jose` or `PyJWT` with `cryptography` backend. JWKS caching: fetch once and cache for 1 hour. The `/health` endpoint is exempt from auth.

---

### E10-S07: RBAC authorization — role-based access control

**As a** platform operator, **I want** role-based access control (admin, analyst, viewer) enforced on API endpoints, **so that** users can only perform actions appropriate to their role.

**Acceptance Criteria:**
1. User roles are extracted from the JWT `roles` claim (configurable claim name).
2. A `require_role(role: str)` FastAPI dependency is available for router-level protection.
3. Role hierarchy: admin > analyst > viewer (admin inherits all lower permissions).
4. Default role assignments: config endpoints → admin, write operations → analyst, read operations → viewer.
5. Tests verify: admin can access all, analyst cannot access config, viewer cannot write, unrecognized role → 403.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E10-S06 |

**Notes:** Roles are managed in the identity provider, not in chiliAI. The application only enforces role claims from tokens.

---

### E10-S08: Structured logging with structlog

**As a** platform operator, **I want** all backend services to produce structured JSON logs with consistent fields (timestamp, level, correlation_id, module, message), **so that** logs are queryable in centralized logging systems.

**Acceptance Criteria:**
1. `structlog` is installed and configured in `api/app.py` and `agent/coordinator.py`.
2. All existing `logging.getLogger()` calls are replaced with `structlog.get_logger()`.
3. Every log entry includes: `timestamp`, `level`, `module`, `correlation_id` (from request or event context), `knowledge_base_id` (when available).
4. JSON output format in production, human-readable format in development (controlled by env var `LOG_FORMAT=json|console`).
5. A test verifies log output structure in JSON mode.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | None |

**Notes:** Use `structlog` processors for timestamp injection and JSON rendering. Bind `correlation_id` at request/event ingress and propagate via contextvars.

---

### E10-S09: Prometheus metrics endpoint

**As a** platform operator, **I want** a `/metrics` endpoint exposing Prometheus-format metrics (request count, latency, pipeline stage duration, error counts), **so that** the platform is observable via standard monitoring tools.

**Acceptance Criteria:**
1. `prometheus-client` is installed.
2. `GET /metrics` returns Prometheus text-format metrics.
3. Instrumented metrics: `http_requests_total` (by method, path, status), `http_request_duration_seconds` (histogram), `pipeline_stage_duration_seconds` (by stage), `pipeline_errors_total` (by stage), `active_alerts_total` (gauge).
4. A FastAPI middleware collects HTTP metrics automatically.
5. A test verifies the `/metrics` endpoint returns valid Prometheus format.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | None |

**Notes:** Use `prometheus_fastapi_instrumentator` for automatic HTTP metrics. Pipeline stage metrics are emitted by the coordinator after each stage completes.

---

### E10-S10: Input validation hardening

**As a** platform developer, **I want** all file-upload and user-input endpoints to enforce strict validation (file size limits, content-type allow list, filename sanitization), **so that** the platform is protected against injection and abuse.

**Acceptance Criteria:**
1. File upload endpoint enforces: max size from config (default 50 MB), content-type allow list (`text/plain`, `application/json`, `text/csv`, `application/vnd.openxmlformats-officedocument.*`, `application/pdf`), filename sanitization (strip path traversal, null bytes, control characters).
2. All string inputs to query endpoints are length-bounded (configurable, default 10,000 chars).
3. RAG question input is trimmed and validated for minimum length (1 char) and maximum length (5,000 chars).
4. Tests verify: oversized file → 413, disallowed content type → 415, malicious filename → sanitized, overlength query → 422.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | None |

**Notes:** Filename sanitization should use `werkzeug.utils.secure_filename` or equivalent logic. Content-type validation must check file magic bytes, not just the header.

---

### E10-S11: Kubernetes manifests and Helm chart

**As a** platform operator, **I want** Kubernetes manifests and a Helm chart for deploying chiliAI (API, worker, Redis, ingress), **so that** the platform can be deployed to any Kubernetes cluster with a single command.

**Acceptance Criteria:**
1. `infra/k8s/` contains base manifests: Deployment, Service, ConfigMap, Secret, HPA for `chili-api`, `chili-worker`, `chili-app`.
2. `infra/helm/chili/` contains a Helm chart with `values.yaml` for customization: image tags, replica counts, resource limits, external service URIs (Redis, graph DB, vector store), auth config.
3. `helm install chili infra/helm/chili/` deploys a working stack with in-memory adapters and default config.
4. Health probes (`/health`) are configured as liveness and readiness probes.
5. A README in `infra/` documents deployment steps.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | None |

**Notes:** Use standard Kubernetes best practices: non-root containers, resource requests/limits, security contexts. Redis is an external dependency — the chart references it but does not deploy it (use Bitnami Redis chart as a dependency or assume external).

---

### E10-S12: TLS/HTTPS and secrets management

**As a** platform operator, **I want** the API gateway to serve traffic over TLS and all secrets (API keys, DB credentials, JWT signing keys) to be loaded from environment variables or a secrets provider, **so that** the platform meets baseline security requirements.

**Acceptance Criteria:**
1. The nginx configuration in `chili_app/nginx.conf` supports TLS termination with configurable cert paths.
2. The Helm chart values support `tls.enabled`, `tls.secretName` for Kubernetes TLS secrets.
3. All backend config fields that reference secrets (LLM API key, DB credentials, Redis password) use `_env_var` pattern — values are read from environment variables, never from config files.
4. A documentation section in `infra/README.md` describes the required secrets and how to provision them.
5. No secrets are committed to the repository or logged.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E10-S11 |

**Notes:** In development, secrets can use `.env` files loaded via `python-dotenv`. In production, use Kubernetes Secrets or an external provider (Vault, AWS Secrets Manager).

---

### E10-S13: E2E integration test suite

**As a** platform developer, **I want** an end-to-end test suite that validates the full pipeline (upload → ingest → graph → analytics → alerts) against in-memory adapters, **so that** cross-module integration is continuously verified.

**Acceptance Criteria:**
1. `tests/e2e/test_full_pipeline.py` starts the API app and worker coordinator with in-memory adapters.
2. The test uploads a document, waits for pipeline completion (polling or event subscription), and asserts: document parsed, entities extracted, graph populated, analytics run, alerts generated.
3. At least three E2E scenarios: single document happy path, multi-document batch, document with extraction errors (graceful degradation).
4. E2E tests run in CI but are tagged `@pytest.mark.e2e` for optional exclusion in local development.
5. Test duration < 30 seconds per scenario.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E7-S10, E8-S07 |

**Notes:** Use `httpx.AsyncClient` with the FastAPI test client. The in-memory event bus enables synchronous event draining for deterministic test execution.

---

### E10-S14: OpenTelemetry distributed tracing

**As a** platform operator, **I want** distributed tracing across API requests and pipeline events using OpenTelemetry, **so that** I can trace a single user action through all backend services and identify performance bottlenecks.

**Acceptance Criteria:**
1. `opentelemetry-api`, `opentelemetry-sdk`, and `opentelemetry-instrumentation-fastapi` are installed.
2. The FastAPI app creates spans for each request, propagating trace context.
3. The worker coordinator creates child spans for each pipeline stage, linked by `correlation_id`.
4. Traces are exported to a configurable OTLP endpoint (default: stdout for development).
5. A test verifies span creation and parent-child relationships.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E10-S08 |

**Notes:** `correlation_id` from the event envelope (E1-S08) maps to the OpenTelemetry trace ID. Configure via `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable.

---

### E10-S15: Security audit checklist and dependency scanning

**As a** platform operator, **I want** automated dependency vulnerability scanning and a documented security audit checklist, **so that** known vulnerabilities are detected early and security posture is reviewable.

**Acceptance Criteria:**
1. GitHub Actions CI includes a `pip-audit` step for Python dependencies and `npm audit` for frontend dependencies.
2. The workflow fails on HIGH or CRITICAL severity vulnerabilities.
3. `docs/security_checklist.md` documents: OWASP Top 10 mitigations, auth configuration, input validation rules, secret management practices, TLS requirements, logging hygiene (no PII in logs).
4. A quarterly review cadence is documented.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E10-S01 |

**Notes:** Use `pip-audit` for Python and `npm audit --audit-level=high` for frontend. Consider adding `trivy` for container image scanning in the Docker build step.
