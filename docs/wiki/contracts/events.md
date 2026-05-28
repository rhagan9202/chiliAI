# Redis Streams Event Payloads

**Verified against codebase:** 2026-05-28
**Source:** `backend/events/types.py`, `backend/events/protocols.py`

All events extend `EventBase`. The `AnyEvent` union type covers all concrete event types. Events are serialized/deserialized via `events/codec.py`.

---

## `EventBase`

```python
class EventBase(BaseModel):
    correlation_id: str         # default: generate_id()
    occurred_at: datetime       # default: utc_now()
    source: str | None = None
    schema_version: int = 1
```

---

## `EventBus` Protocol

```python
class EventBus(Protocol):
    def publish(self, event: AnyEvent) -> str | None: ...
    def ensure_consumer_group(self, event_types: list[str], *, consumer_group: str) -> None: ...
    def consume(
        self,
        event_types: list[str],
        *,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
        limit: int = 1,
        block_ms: int | None = None,
    ) -> list[EventDelivery]: ...
    def ack(self, deliveries: list[EventDelivery]) -> None: ...
    def publish_to_dlq(self, event: AnyEvent, error_info: DlqErrorInfo) -> str | None: ...
```

### `EventDelivery`
```python
@dataclass(frozen=True, slots=True)
class EventDelivery:
    event: AnyEvent
    event_id: str | None = None
    stream: str | None = None
    consumer_group: str | None = None
```

---

## Document Pipeline Events (ingestion flow)

| Event Type | `event_type` literal | Publisher | Consumer |
|------------|---------------------|-----------|----------|
| `DocumentsUploadedEvent` | `"documents.uploaded"` | KB router (on file upload) | Worker: parse step |
| `DocumentsParsedEvent` | `"documents.parsed"` | Worker | Worker: chunk step |
| `DocumentsChunkedEvent` | `"documents.chunked"` | Worker | Worker: extract step |
| `EntitiesExtractedEvent` | `"entities.extracted"` | Worker | Worker: validate step |
| `EntitiesValidatedEvent` | `"entities.validated"` | Worker | Worker: graph-update step |
| `GraphUpdatedEvent` | `"graph.updated"` | Worker | Worker: embed step |
| `EmbeddingsCompleteEvent` | `"embeddings.complete"` | Worker | Worker: vector-index step |
| `VectorsIndexedEvent` | `"vectors.indexed"` | Worker | Worker: kb-ready step |
| `VectorsDeletedEvent` | `"vectors.deleted"` | Worker | Informational vector cleanup event |
| `KnowledgeBaseReadyEvent` | `"kb.ready"` | Worker | API projection |
| `DocumentsFailedEvent` | `"documents.failed"` | Worker | API projection |
| `PipelineProgressEvent` | `"pipeline.progress"` | Worker | SSE/WS hub |

### `DocumentsUploadedEvent`
```python
event_type: Literal["documents.uploaded"] = "documents.uploaded"
documents: list[DocumentReference]
```

### `DocumentReference`
```python
class DocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    filename: str | None = None
    content_type: str | None = None
    storage_key: str | None = None
    uri: str | None = None
    document_format: str | None = None
    source_type: str | None = None
    size_bytes: int | None = None
```

### `DocumentsParsedEvent`
```python
event_type: Literal["documents.parsed"] = "documents.parsed"
documents: list[ParsedDocumentReference]
# ParsedDocumentReference adds: parsed_document_id, parser_name, parser_version, parsed_document_storage_key
```

### `DocumentsChunkedEvent`
```python
event_type: Literal["documents.chunked"] = "documents.chunked"
documents: list[ChunkedDocumentReference]
# ChunkedDocumentReference adds: chunk_count, strategy, chunks_storage_key
```

### `EntitiesExtractedEvent`
```python
event_type: Literal["entities.extracted"] = "entities.extracted"
documents: list[ExtractedDocumentReference]
# ExtractedDocumentReference adds: extraction_result_id, entity_count, relationship_count, extraction_storage_key
```

### `EntitiesValidatedEvent`
```python
event_type: Literal["entities.validated"] = "entities.validated"
documents: list[ValidatedDocumentReference]
# ValidatedDocumentReference adds: validation_report_id, valid_entity_count, valid_relationship_count,
#   entity_error_count, relationship_error_count, validation_storage_key
```

### `GraphUpdatedEvent`
```python
event_type: Literal["graph.updated"] = "graph.updated"
documents: list[GraphUpdatedDocumentReference]
# GraphUpdatedDocumentReference adds: upserted_entity_count, upserted_relationship_count, graph_update_storage_key
```

### `EmbeddingsCompleteEvent`
```python
event_type: Literal["embeddings.complete"] = "embeddings.complete"
documents: list[EmbeddingsCompleteDocumentReference]
# adds: entity_count, graph_update_storage_key, embeddings_storage_key (required)
```

### `VectorsIndexedEvent`
```python
event_type: Literal["vectors.indexed"] = "vectors.indexed"
records: list[VectorIndexedReference]     # individual record-level entries
documents: list[VectorsIndexedDocumentReference]   # document-level entries
```

### `VectorsDeletedEvent`
```python
event_type: Literal["vectors.deleted"] = "vectors.deleted"
knowledge_base_id: str
deleted_count: int   # >= 0
```

### `KnowledgeBaseReadyEvent`
```python
event_type: Literal["kb.ready"] = "kb.ready"
knowledge_bases: list[KnowledgeBaseReadyReference]
# KnowledgeBaseReadyReference: knowledge_base_id, entity_count, relationship_count, vector_count
```

---

## Knowledge Base Lifecycle Events

### `KnowledgeBaseCreatedEvent`
```python
event_type: Literal["kb.create"] = "kb.create"
knowledge_base_id: str
```

### `KnowledgeBaseDeletedEvent`
```python
event_type: Literal["kb.delete"] = "kb.delete"
knowledge_base_id: str
cleanup_pending: bool = False   # True when one or more cascade steps failed (207 partial delete)
```

---

## Analytics / Monitoring Events

| Event Type | `event_type` literal |
|------------|---------------------|
| `TimeseriesAnalyzedEvent` | `"timeseries.analyzed"` |
| `GnnAnalyzedEvent` | `"gnn.analyzed"` |
| `RiskScoredEvent` | `"risk.scored"` |
| `ExplainabilityGeneratedEvent` | `"explainability.generated"` |
| `AlertsCreatedEvent` | `"alerts.created"` |
| `AlertCreatedEvent` | `"alert.created"` (single alert, for WS push) |
| `AnalysisFailedEvent` | `"analysis.failed"` |

### `RiskScoredEvent`
```python
event_type: Literal["risk.scored"] = "risk.scored"
assessments: list[RiskScoredReference]

class RiskScoredReference(BaseModel):
    knowledge_base_id: str
    request_id: str
    entity_id: str
    overall_score: float     # [0.0, 1.0]
    risk_level: str
    factor_count: int        # >= 0
    factors: list[RiskFactorReference]
```

### `AlertsCreatedEvent`
```python
event_type: Literal["alerts.created"] = "alerts.created"
alerts: list[AlertCreatedReference]

class AlertCreatedReference(BaseModel):
    knowledge_base_id: str
    alert_id: str
    entity_id: str
    severity: str
    evidence_pack_id: str | None = None
    entity_type: str = ""
    status: str = "open"
    title: str = ""
    reasoning: str = ""
    metric_name: str = ""
```

---

## Records Event

### `RecordsIngestedEvent`
```python
event_type: Literal["records.ingested"] = "records.ingested"
knowledge_base_id: str
feed_name: str
record_type: str
record_count: int   # >= 0
```
Published by `RecordsService.register_records()`. Worker Flow 1 handler uses `feed_name` + `correlation_id` to resolve and process the batch.

---

## Legacy Claims Events

```python
class ClaimsReceivedEvent(EventBase):
    event_type: Literal["claims.received"] = "claims.received"
    batch_id: str
    source: str | None = None

class ClaimsIngestedEvent(EventBase):
    event_type: Literal["claims.ingested"] = "claims.ingested"
    batch_id: str
    record_count: int   # >= 0
```

---

## Observability Events (not pipeline events)

```python
class LlmCompletedEvent:      event_type = "llm.completed"
class EmbeddingsGeneratedEvent: event_type = "embeddings.generated"
class RagCompletedEvent:      event_type = "rag.completed"
class AgentWorkflowStartedEvent: event_type = "agent.workflow.started"
```

---

## `AnyEvent` Union

The discriminated union of all event types. Used as the `event` field in `EventDelivery`:

```python
AnyEvent = (
    KnowledgeBaseCreatedEvent | KnowledgeBaseDeletedEvent |
    DocumentsUploadedEvent | DocumentsParsedEvent | DocumentsChunkedEvent |
    EntitiesExtractedEvent | EntitiesValidatedEvent | GraphUpdatedEvent |
    EmbeddingsCompleteEvent | VectorsIndexedEvent | VectorsDeletedEvent | KnowledgeBaseReadyEvent |
    LlmCompletedEvent | EmbeddingsGeneratedEvent | RagCompletedEvent |
    TimeseriesAnalyzedEvent | GnnAnalyzedEvent | RiskScoredEvent |
    ExplainabilityGeneratedEvent | AgentWorkflowStartedEvent |
    AlertsCreatedEvent | AlertCreatedEvent | PipelineProgressEvent |
    AnalysisFailedEvent | DocumentsFailedEvent |
    ClaimsReceivedEvent | ClaimsIngestedEvent | RecordsIngestedEvent
)
```

## Adapters

| Backend | Class | Config key |
|---------|-------|-----------|
| In-memory | `events/adapters/in_memory.py::InMemoryEventBus` | `backend = "in_memory"` |
| Redis Streams | `events/adapters/redis_streams.py` | `backend = "redis"` |

Factory: `events/runtime.py` — reads `EventBusConfig` from `DomainConfig`.
