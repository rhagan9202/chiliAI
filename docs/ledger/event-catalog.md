# Event Catalog

**Generated:** 2026-05-22 (merge commit `acae4ac`) · **Union reconciled:** 2026-08-07 (34 members)
**Source:** `backend/events/types.py` — re-derive before relying on completeness; the per-event sections below still reflect the 2026-05-22 sweep.

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

> `handle_records_ingested` maps rows → entities/relationships → graph upsert, also embeds+indexes records-derived entities into the vector store [enhanced 2026-05-22], and derives observations → `PostgresObservationStore`. Since analytics.34 (2026-07-24) the handler also runs best-effort policy/peerstats/timeseries stages and an in-process Flow B analytics fan-out via `handle_graph_updated_for_analytics` (in-memory `GraphUpdatedEvent` carrying inline `upserted_entity_ids`; never published) — see `docs/wiki/contracts/events.md`.

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

**34 members** as of 2026-08-07. Do not copy the list below into a `match` or
an exhaustiveness check without re-deriving it — this block listed 28 while the
code had 32, so anything built from it silently dropped four event types.
Ground truth:

```bash
cd backend && python -c "
from typing import get_args
import events.types as t
print(len(get_args(t.AnyEvent)))"
```

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
    ClaimsReceivedEvent | ClaimsIngestedEvent | RecordsIngestedEvent |
    # --- previously undocumented ---
    ConfigUpdatedEvent | DocumentsExtractionWarningEvent |
    IdentityLinkDecisionRecordedEvent | ScoreRunStatusChangedEvent |
    # --- executor events ---
    ScoreBatchQueuedEvent | ScoreRunQueuedEvent
)
```

### Previously undocumented events

| Event | `event_type` | Notes |
|---|---|---|
| `ConfigUpdatedEvent` | `config.updated` | Emitted on domain-pack apply/switch. |
| `DocumentsExtractionWarningEvent` | `documents.extraction_warning` | Non-fatal extraction warnings (ingestion.35). |
| `IdentityLinkDecisionRecordedEvent` | `identity.link_decision.recorded` | SAFE-CMS-012 steward merge/split. **Published with no consumer** — codec-registered and emitted, but nothing subscribes, so identity changes do not propagate to graph or read models. |
| `ScoreRunStatusChangedEvent` | `score_run.status_changed` | SAFE-CMS-002 score-run lifecycle. Published by `ScoreRunService` for operator/UI refresh; not itself a work trigger. |
| `ScoreRunQueuedEvent` | `score.run.queued` | A run started without an explicit entity list needs enumerating. Consumed by `analytics/score_runs/executor.py`, which lists the KB's entities and creates the batches — enumeration in the HTTP request failed large KBs before any work was durable. |
| `ScoreBatchQueuedEvent` | `score.batch.queued` | One score-all batch ready to execute. Consumed by `analytics/score_runs/executor.py`. Carries identifiers only — the executor reloads state, so a redelivered event cannot resurrect a stale snapshot. |
