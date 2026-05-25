# Event Catalog

**Generated:** 2026-05-22 (merge commit `acae4ac`)
**Source:** `backend/events/types.py`

All events extend `EventBase` which carries `correlation_id`, `occurred_at`, `source`, and `schema_version: int = 1`.

---

## Knowledge Base Lifecycle

| Event | `event_type` literal | Payload fields | Publisher | Consumer |
|-------|---------------------|----------------|-----------|----------|
| `KnowledgeBaseCreatedEvent` | `kb.create` | `knowledge_base_id: str` | `POST /knowledgebases` | `agent.coordinator.handle_kb_created` |
| `KnowledgeBaseDeletedEvent` | `kb.delete` | `knowledge_base_id: str`, `cleanup_pending: bool = False` [added 2026-05-22] | `DELETE /knowledgebases/{id}` | `agent.coordinator.handle_knowledge_base_deleted` |

---

## Document Pipeline (Flow A)

| Event | `event_type` literal | Key payload fields | Publisher | Consumer |
|-------|---------------------|--------------------|-----------|----------|
| `DocumentsUploadedEvent` | `documents.uploaded` | `documents: list[DocumentReference]` | `POST /knowledgebases/{id}/documents` | `agent.coordinator.handle_documents_uploaded` |
| `DocumentsParsedEvent` | `documents.parsed` | `documents: list[ParsedDocumentReference]` | worker (ingestion step) | worker (chunking step) |
| `DocumentsChunkedEvent` | `documents.chunked` | `documents: list[ChunkedDocumentReference]` | worker | worker (extraction step) |
| `EntitiesExtractedEvent` | `entities.extracted` | `documents: list[ExtractedDocumentReference]` | worker | worker (validation step) |
| `EntitiesValidatedEvent` | `entities.validated` | `documents: list[ValidatedDocumentReference]` | worker | worker (graph upsert step) |
| `GraphUpdatedEvent` | `graph.updated` | `documents: list[GraphUpdatedDocumentReference]` | worker | worker (embed step) + `handle_graph_updated_for_analytics` |
| `EmbeddingsCompleteEvent` | `embeddings.complete` | `documents: list[EmbeddingsCompleteDocumentReference]` | worker | worker (vector index step) |
| `VectorsIndexedEvent` | `vectors.indexed` | `records: list[VectorIndexedReference]`, `documents: list[VectorsIndexedDocumentReference]` | worker | worker (kb.ready check) |
| `VectorsDeletedEvent` | `vectors.deleted` | `knowledge_base_id: str`, `deleted_count: int` | worker | (informational) |
| `KnowledgeBaseReadyEvent` | `kb.ready` | `knowledge_bases: list[KnowledgeBaseReadyReference]` | worker | SSE / WebSocket push |
| `DocumentsFailedEvent` | `documents.failed` | `documents: list[DocumentFailureReference]` | worker (DLQ) | SSE / WebSocket push |

---

## Structured Records Pipeline (Flow 1)

| Event | `event_type` literal | Payload fields | Publisher | Consumer |
|-------|---------------------|----------------|-----------|----------|
| `RecordsIngestedEvent` | `records.ingested` | `knowledge_base_id: str`, `feed_name: str`, `record_type: str`, `record_count: int` | `RecordsService.register_records()` | `agent.coordinator.handle_records_ingested` |

> `handle_records_ingested` maps rows → entities/relationships → graph upsert, also embeds+indexes records-derived entities into the vector store [enhanced 2026-05-22], and derives observations → `PostgresObservationStore`.

---

## LLM & Embedding Telemetry

| Event | `event_type` literal | Key payload fields |
|-------|---------------------|-------------------|
| `LlmCompletedEvent` | `llm.completed` | `completions: list[LlmCompletionReference]` (`knowledge_base_id`, `request_id`, `model_name`, `provider`, `message_count`, `completion_length`) |
| `EmbeddingsGeneratedEvent` | `embeddings.generated` | `batches: list[EmbeddingGeneratedReference]` (`knowledge_base_id`, `request_id`, `item_count`, `dimensions`, `model_name`) |

---

## RAG

| Event | `event_type` literal | Key payload fields |
|-------|---------------------|-------------------|
| `RagCompletedEvent` | `rag.completed` | `replies: list[RagCompletionReference]` (`knowledge_base_id`, `request_id`, `provider`, `model_name`, `context_item_count`, `citation_count`, `answer_length`) |

---

## Analytics Pipeline

| Event | `event_type` literal | Key payload fields |
|-------|---------------------|-------------------|
| `TimeseriesAnalyzedEvent` | `timeseries.analyzed` | `analyses: list[TimeseriesAnalyzedReference]` |
| `GnnAnalyzedEvent` | `gnn.analyzed` | `analyses: list[GnnAnalyzedReference]` |
| `RiskScoredEvent` | `risk.scored` | `assessments: list[RiskScoredReference]` (incl. `factors: list[RiskFactorReference]`) |
| `ExplainabilityGeneratedEvent` | `explainability.generated` | `evidence_packs: list[ExplainabilityGeneratedReference]` |

---

## Alerts & Monitoring

| Event | `event_type` literal | Key payload fields |
|-------|---------------------|-------------------|
| `AlertsCreatedEvent` | `alerts.created` | `alerts: list[AlertCreatedReference]` (batch) |
| `AlertCreatedEvent` | `alert.created` | `alert: Alert` (single-alert, for WebSocket push) |

---

## Agent / Workflow

| Event | `event_type` literal | Key payload fields |
|-------|---------------------|-------------------|
| `AgentWorkflowStartedEvent` | `agent.workflow.started` | `workflows: list[AgentWorkflowStartedReference]` |
| `PipelineProgressEvent` | `pipeline.progress` | `knowledge_base_id: str`, `stage: str`, `progress: float`, `message: str \| None` |
| `AnalysisFailedEvent` | `analysis.failed` | `knowledge_base_id: str`, `entity_id: str`, `stage: str`, `error_message: str` |

---

## Legacy Claims Events

| Event | `event_type` literal | Notes |
|-------|---------------------|-------|
| `ClaimsReceivedEvent` | `claims.received` | `batch_id: str`, `source: str \| None` |
| `ClaimsIngestedEvent` | `claims.ingested` | `batch_id: str`, `record_count: int` |

---

## `AnyEvent` Union

```python
AnyEvent = (
    KnowledgeBaseCreatedEvent | KnowledgeBaseDeletedEvent |
    DocumentsUploadedEvent | DocumentsParsedEvent | DocumentsChunkedEvent |
    EntitiesExtractedEvent | EntitiesValidatedEvent | GraphUpdatedEvent |
    EmbeddingsCompleteEvent | VectorsIndexedEvent | VectorsDeletedEvent |
    KnowledgeBaseReadyEvent | LlmCompletedEvent | EmbeddingsGeneratedEvent |
    RagCompletedEvent | TimeseriesAnalyzedEvent | GnnAnalyzedEvent |
    RiskScoredEvent | ExplainabilityGeneratedEvent | AgentWorkflowStartedEvent |
    AlertsCreatedEvent | AlertCreatedEvent | PipelineProgressEvent |
    AnalysisFailedEvent | DocumentsFailedEvent |
    ClaimsReceivedEvent | ClaimsIngestedEvent | RecordsIngestedEvent
)
```
