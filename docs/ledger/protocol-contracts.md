# Protocol Contracts

**Generated:** 2026-05-22 (merge commit `acae4ac`)

Every `Protocol` in `backend/`. Columns: protocol name, defined in, methods, implementing adapters.

---

## Service-Level Protocols

### `GraphServiceProtocol` (`graph/protocols.py`)

| Method | Signature |
|--------|-----------|
| `upsert_task` | `(task: GraphBuildTask) -> GraphBuildReceipt` |
| `get_entity` | `(knowledge_base_ids: list[str], entity_id: str) -> Entity \| None` |
| `update_entity_properties` | `(knowledge_base_id: str, entity_id: str, properties: dict) -> Entity \| None` |
| `query_neighborhood` | `(knowledge_base_id: str, entity_id: str, depth: int) -> NeighborhoodResult` |
| `search_entities` | `(knowledge_base_ids: list[str], query: str, ...) -> EntitySearchResult` |
| `compute_metrics` | `(knowledge_base_id: str) -> GraphMetrics` |
| `delete_knowledge_base` | `(knowledge_base_id: str) -> None` |
| `delete_by_source_document` | `(knowledge_base_id: str, source_document_id: str) -> GraphDeleteByProvenance` [added 2026-05-22] |

**Implementing service:** `graph.service.GraphService`

### `VectorServiceProtocol` (`vectorstore/protocols.py`)

| Method | Signature |
|--------|-----------|
| `index` | `(request: VectorIndexRequest) -> list[VectorIndexReceipt]` |
| `search` | `(request: VectorSearchRequest) -> VectorSearchResponse` |
| `batch_search` | `(requests: list[VectorSearchRequest]) -> list[VectorSearchResponse]` |
| `get_record` | `(knowledge_base_id: str, record_id: str) -> VectorRecord \| None` |
| `count` | `(knowledge_base_id: str) -> int` |
| `delete_record` | `(knowledge_base_id: str, record_id: str) -> bool` |
| `delete_knowledge_base` | `(knowledge_base_id: str) -> VectorDeleteResponse` |
| `delete_by_source_document` | `(knowledge_base_id: str, source_document_id: str) -> VectorDeleteResponse` [added 2026-05-22] |

**Implementing service:** `vectorstore.service.VectorService`

### `EmbeddingsServiceProtocol` (`embeddings/protocols.py`)

| Method | Signature |
|--------|-----------|
| `embed` | `(request: EmbedRequest) -> EmbedResponse` |

**Implementing service:** `embeddings.service.EmbeddingsService`

### `LlmServiceProtocol` (`llm/protocols.py`)

| Method | Signature |
|--------|-----------|
| `generate` | `(request: GenerateRequest) -> CompletionResponse` |
| `generate_stream` | `(request: GenerateRequest) -> AsyncIterator[str]` |

**Implementing service:** `llm.service.LlmService`

### `RagServiceProtocol` (`rag/protocols.py`)

| Method | Signature |
|--------|-----------|
| `answer` | `(request: RagQueryRequest) -> RagQueryResponse` |
| `answer_question` | `(knowledge_base_id: str, question: str, ...) -> RagQueryResponse` |
| `stream_answer` | `(request: RagQueryRequest) -> AsyncIterator[str]` |

**Implementing service:** `rag.service.RagService`

### `RecordsServiceProtocol` (`records/protocols.py`)

| Method | Signature |
|--------|-----------|
| `register_records` | `(knowledge_base_id: str, submission: RecordSubmission) -> RecordIngestReceipt` |

**Implementing service:** `records.service.RecordsService`

### `AgentServiceProtocol` (`agent/protocols.py`)

| Method | Signature |
|--------|-----------|
| `start_workflow` | `(request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse` |
| `get_workflow_status` | `(workflow_id: str) -> WorkflowRun` |
| `list_workflows` | `(knowledge_base_id: str \| None, ...) -> list[WorkflowRun]` |
| `cancel_workflow` | `(workflow_id: str) -> WorkflowRun` |

**Implementing service:** `agent.service.AgentService`

### `MonitoringServiceProtocol` / `AlertsServiceProtocol` (`monitoring/protocols.py`)

`MonitoringServiceProtocol`:
- `evaluate(request: MonitoringEvaluationRequest) -> MonitoringEvaluationResponse`

`AlertsServiceProtocol`:
- `list_alerts(request: AlertListRequest) -> AlertListResponse`
- `acknowledge_alert(alert_id: str) -> Alert`
- `resolve_alert(alert_id: str, request: ResolutionRequest) -> Alert`

---

## Adapter-Level Protocols

### `GraphRepository` (`graph/adapters/protocols.py`)

Full graph DB CRUD + `delete_by_source_document`. Implemented by `InMemoryGraphRepository` and `Neo4jGraphRepository`.

### `VectorStoreProtocol` (`vectorstore/adapters/protocols.py`)

Full vector store CRUD + `delete_by_source_document`. Implemented by `InMemoryVectorStore` and `QdrantVectorStore`.

### `LlmClientProtocol` (`llm/adapters/protocols.py`)

- `generate(request: GenerationRequest) -> GenerationResult`
- `generate_stream(request: GenerationRequest) -> AsyncIterator[str]` (optional)

Implemented by: `InMemoryLlmClient`, `OpenAiLlmClient`, `AnthropicLlmClient`, `OllamaLlmClient` [2026-05-22], `FallbackLlmClient` [2026-05-22].

### `EmbeddingsAdapterProtocol` (`embeddings/adapters/protocols.py`)

- `embed(texts: list[str], model_name: str \| None) -> list[list[float]]`

Implemented by: `InMemoryEmbeddingsAdapter`, `OpenAiEmbeddingsAdapter`, `SentenceTransformersAdapter`.

### `RawRecordStore` (`records/adapters/protocols.py`)

- `persist(records: list[RawRecord]) -> int`
- `load_batch(*, knowledge_base_id: str, correlation_id: str) -> list[RawRecord]`
- `load_for_kb(*, knowledge_base_id: str) -> list[RawRecord]`
- `delete_by_kb(knowledge_base_id: str) -> int` [added 2026-05-22]
- `was_submitted(*, knowledge_base_id: str, submission_hash: str) -> bool`
- `record_submission(*, knowledge_base_id: str, submission_hash: str, correlation_id: str) -> None`

Implemented by: `InMemoryRawRecordStore`, `PostgresRawRecordStore`.

### `RecordSourceProtocol` (`records/adapters/protocols.py`)

- `read_rows(raw: bytes) -> list[dict[str, object]]`

Implemented by: `CsvFileSource`, `JsonlFileSource`, `ApiPushSource`.

### `ObjectStore` (`storage/protocols.py`)

- `put_bytes(key: str, content: bytes, *, media_type: str | None = None, metadata: dict[str, object] | None = None) -> StoredObjectWriteResult`
- `get_bytes(key: str) -> StoredObject`
- `delete(key: str) -> None`
- `exists(key: str) -> bool`
- `list_keys(prefix: str) -> list[str]`

Implemented by: `InMemoryObjectStore`, `LocalFsObjectStore`, `S3ObjectStore`.

### `EventBus` (`events/protocols.py`)

- `publish(event: AnyEvent) -> None`
- `subscribe(event_types: list[str], handler: Callable) -> None`
- `consume(group: str, consumer: str, ...) -> Iterator[AnyEvent]`

Implemented by: `InMemoryEventBus`, `RedisStreamsEventBus`.

### `ConnectionProvider` (`database/protocols.py`)

- `connection() -> AbstractContextManager[DatabaseConnection]`
- `close() -> None`

`DatabaseConnection`:
- `cursor() -> DatabaseCursor`
- `execute(query, params) -> DatabaseCursor`
- `commit() -> None`, `rollback() -> None`

Implemented by: `PsycopgConnectionProvider`, `InMemoryConnectionProvider`.

### `WorkflowRunStoreProtocol` (`agent/adapters/protocols.py`)

Workflow lifecycle CRUD. Implemented by: `InMemoryWorkflowRunStore`, `RedisWorkflowRunStore`.

### `EntityMetricRepository` (`analytics/metrics/adapters/protocols.py`)

- `append_history(snapshot: EntityMetricSnapshot) -> None`
- `upsert_current(metric: EntityMetric) -> None`
- `get_current(entity_id: str, metric_name: str) -> EntityMetric \| None`

Implemented by: `InMemoryEntityMetricRepository`, `PostgresEntityMetricRepository`.
