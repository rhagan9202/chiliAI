"""Event payload types for the staged backend workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from shared.types import Alert
from shared.utils import generate_id, utc_now


class EventBase(BaseModel):
    """Base event envelope."""

    correlation_id: str = Field(default_factory=generate_id)
    occurred_at: datetime = Field(default_factory=utc_now)
    source: str | None = None
    schema_version: int = 1


class KnowledgeBaseCreatedEvent(EventBase):
    event_type: Literal["kb.create"] = "kb.create"
    knowledge_base_id: str


class KnowledgeBaseDeletedEvent(EventBase):
    event_type: Literal["kb.delete"] = "kb.delete"
    knowledge_base_id: str


class DocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    filename: str | None = None
    content_type: str | None = None
    storage_key: str | None = None
    uri: str | None = None
    document_format: str | None = None
    size_bytes: int | None = None


class DocumentsUploadedEvent(EventBase):
    event_type: Literal["documents.uploaded"] = "documents.uploaded"
    documents: list[DocumentReference]


class ParsedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    parser_name: str
    parser_version: str | None = None
    document_format: str | None = None
    storage_key: str | None = None
    parsed_document_storage_key: str | None = None


class DocumentsParsedEvent(EventBase):
    event_type: Literal["documents.parsed"] = "documents.parsed"
    documents: list[ParsedDocumentReference]


class ChunkedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    chunk_count: int = Field(ge=0)
    strategy: str
    storage_key: str | None = None
    parsed_document_storage_key: str | None = None
    chunks_storage_key: str | None = None


class DocumentsChunkedEvent(EventBase):
    event_type: Literal["documents.chunked"] = "documents.chunked"
    documents: list[ChunkedDocumentReference]


class ExtractedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    storage_key: str | None = None
    parsed_document_storage_key: str | None = None
    chunks_storage_key: str | None = None
    extraction_storage_key: str | None = None


class EntitiesExtractedEvent(EventBase):
    event_type: Literal["entities.extracted"] = "entities.extracted"
    documents: list[ExtractedDocumentReference]


class ValidatedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    valid_entity_count: int = Field(ge=0)
    valid_relationship_count: int = Field(ge=0)
    entity_error_count: int = Field(ge=0)
    relationship_error_count: int = Field(ge=0)
    storage_key: str | None = None
    parsed_document_storage_key: str | None = None
    chunks_storage_key: str | None = None
    extraction_storage_key: str | None = None
    validation_storage_key: str | None = None


class EntitiesValidatedEvent(EventBase):
    event_type: Literal["entities.validated"] = "entities.validated"
    documents: list[ValidatedDocumentReference]


class GraphUpdatedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    upserted_entity_count: int = Field(ge=0)
    upserted_relationship_count: int = Field(ge=0)
    validation_storage_key: str | None = None
    graph_update_storage_key: str | None = None


class GraphUpdatedEvent(EventBase):
    event_type: Literal["graph.updated"] = "graph.updated"
    documents: list[GraphUpdatedDocumentReference]


class EmbeddingsCompleteDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    entity_count: int = Field(ge=0)
    graph_update_storage_key: str
    embeddings_storage_key: str


class EmbeddingsCompleteEvent(EventBase):
    event_type: Literal["embeddings.complete"] = "embeddings.complete"
    documents: list[EmbeddingsCompleteDocumentReference]


class VectorIndexedReference(BaseModel):
    knowledge_base_id: str
    record_id: str
    content_id: str
    dimension: int = Field(gt=0)


class VectorsIndexedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    vector_count: int = Field(ge=0)
    embeddings_storage_key: str
    record_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class VectorsIndexedEvent(EventBase):
    event_type: Literal["vectors.indexed"] = "vectors.indexed"
    records: list[VectorIndexedReference] = Field(
        default_factory=lambda: cast(list[VectorIndexedReference], [])
    )
    documents: list[VectorsIndexedDocumentReference] = Field(
        default_factory=lambda: cast(list[VectorsIndexedDocumentReference], [])
    )


class KnowledgeBaseReadyReference(BaseModel):
    knowledge_base_id: str
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    vector_count: int = Field(ge=0)


class KnowledgeBaseReadyEvent(EventBase):
    event_type: Literal["kb.ready"] = "kb.ready"
    knowledge_bases: list[KnowledgeBaseReadyReference]


class LlmCompletionReference(BaseModel):
    knowledge_base_id: str | None = None
    request_id: str
    model_name: str
    provider: str
    message_count: int = Field(ge=1)
    completion_length: int = Field(ge=0)


class LlmCompletedEvent(EventBase):
    event_type: Literal["llm.completed"] = "llm.completed"
    completions: list[LlmCompletionReference]


class EmbeddingGeneratedReference(BaseModel):
    knowledge_base_id: str | None = None
    request_id: str
    item_count: int = Field(ge=1)
    dimensions: int = Field(gt=0)
    model_name: str


class EmbeddingsGeneratedEvent(EventBase):
    event_type: Literal["embeddings.generated"] = "embeddings.generated"
    batches: list[EmbeddingGeneratedReference]


class RagCompletionReference(BaseModel):
    knowledge_base_id: str
    request_id: str
    provider: str
    model_name: str
    context_item_count: int = Field(ge=0)
    citation_count: int = Field(ge=0)
    answer_length: int = Field(ge=0)


class RagCompletedEvent(EventBase):
    event_type: Literal["rag.completed"] = "rag.completed"
    replies: list[RagCompletionReference]


class TimeseriesAnalyzedReference(BaseModel):
    knowledge_base_id: str
    request_id: str
    entity_id: str
    metric_name: str
    observation_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)


class TimeseriesAnalyzedEvent(EventBase):
    event_type: Literal["timeseries.analyzed"] = "timeseries.analyzed"
    analyses: list[TimeseriesAnalyzedReference]


class GnnAnalyzedReference(BaseModel):
    knowledge_base_id: str
    request_id: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    predicted_link_count: int = Field(ge=0)
    cluster_count: int = Field(ge=0)


class GnnAnalyzedEvent(EventBase):
    event_type: Literal["gnn.analyzed"] = "gnn.analyzed"
    analyses: list[GnnAnalyzedReference]


class RiskScoredReference(BaseModel):
    knowledge_base_id: str
    request_id: str
    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    factor_count: int = Field(ge=0)


class RiskScoredEvent(EventBase):
    event_type: Literal["risk.scored"] = "risk.scored"
    assessments: list[RiskScoredReference]


class ExplainabilityGeneratedReference(BaseModel):
    knowledge_base_id: str
    request_id: str
    alert_id: str
    evidence_pack_id: str
    evidence_item_count: int = Field(ge=0)
    subgraph_node_count: int = Field(ge=0)
    subgraph_edge_count: int = Field(ge=0)


class ExplainabilityGeneratedEvent(EventBase):
    event_type: Literal["explainability.generated"] = "explainability.generated"
    evidence_packs: list[ExplainabilityGeneratedReference]


class AgentWorkflowStartedReference(BaseModel):
    workflow_id: str
    knowledge_base_id: str
    trigger_event_type: str
    step_count: int = Field(ge=1)
    status: str


class AgentWorkflowStartedEvent(EventBase):
    event_type: Literal["agent.workflow.started"] = "agent.workflow.started"
    workflows: list[AgentWorkflowStartedReference]


class AlertCreatedReference(BaseModel):
    knowledge_base_id: str
    alert_id: str
    entity_id: str
    severity: str
    evidence_pack_id: str | None = None


class AlertsCreatedEvent(EventBase):
    event_type: Literal["alerts.created"] = "alerts.created"
    alerts: list[AlertCreatedReference]


class AlertCreatedEvent(EventBase):
    """Single-alert event surfaced to real-time WebSocket subscribers."""

    event_type: Literal["alert.created"] = "alert.created"
    alert: Alert


class PipelineProgressEvent(EventBase):
    """Pipeline stage progress event for a knowledge base ingestion run."""

    event_type: Literal["pipeline.progress"] = "pipeline.progress"
    knowledge_base_id: str
    stage: str
    progress: float = Field(ge=0.0, le=1.0)
    message: str | None = None


class AnalysisFailedEvent(EventBase):
    """Emitted when an analytics pipeline stage fails for a single entity."""

    event_type: Literal["analysis.failed"] = "analysis.failed"
    knowledge_base_id: str
    entity_id: str
    stage: str
    error_message: str


class DocumentFailureReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    error_message: str
    storage_key: str | None = None


class DocumentsFailedEvent(EventBase):
    event_type: Literal["documents.failed"] = "documents.failed"
    documents: list[DocumentFailureReference]


class ClaimsReceivedEvent(EventBase):
    event_type: Literal["claims.received"] = "claims.received"
    batch_id: str
    source: str | None = None


class ClaimsIngestedEvent(EventBase):
    event_type: Literal["claims.ingested"] = "claims.ingested"
    batch_id: str
    record_count: int = Field(ge=0)


AnyEvent = (
    KnowledgeBaseCreatedEvent
    | KnowledgeBaseDeletedEvent
    | DocumentsUploadedEvent
    | DocumentsParsedEvent
    | DocumentsChunkedEvent
    | EntitiesExtractedEvent
    | EntitiesValidatedEvent
    | GraphUpdatedEvent
    | EmbeddingsCompleteEvent
    | VectorsIndexedEvent
    | KnowledgeBaseReadyEvent
    | LlmCompletedEvent
    | EmbeddingsGeneratedEvent
    | RagCompletedEvent
    | TimeseriesAnalyzedEvent
    | GnnAnalyzedEvent
    | RiskScoredEvent
    | ExplainabilityGeneratedEvent
    | AgentWorkflowStartedEvent
    | AlertsCreatedEvent
    | AlertCreatedEvent
    | PipelineProgressEvent
    | AnalysisFailedEvent
    | DocumentsFailedEvent
    | ClaimsReceivedEvent
    | ClaimsIngestedEvent
)


__all__ = [
    "AgentWorkflowStartedEvent",
    "AgentWorkflowStartedReference",
    "AlertCreatedEvent",
    "AlertCreatedReference",
    "AlertsCreatedEvent",
    "AnalysisFailedEvent",
    "AnyEvent",
    "ChunkedDocumentReference",
    "ClaimsIngestedEvent",
    "ClaimsReceivedEvent",
    "DocumentFailureReference",
    "DocumentReference",
    "DocumentsChunkedEvent",
    "DocumentsFailedEvent",
    "DocumentsParsedEvent",
    "DocumentsUploadedEvent",
    "EmbeddingsCompleteDocumentReference",
    "EmbeddingsCompleteEvent",
    "EmbeddingGeneratedReference",
    "EmbeddingsGeneratedEvent",
    "EntitiesExtractedEvent",
    "EntitiesValidatedEvent",
    "EventBase",
    "ExplainabilityGeneratedEvent",
    "ExplainabilityGeneratedReference",
    "ExtractedDocumentReference",
    "GnnAnalyzedEvent",
    "GnnAnalyzedReference",
    "GraphUpdatedDocumentReference",
    "GraphUpdatedEvent",
    "KnowledgeBaseCreatedEvent",
    "KnowledgeBaseDeletedEvent",
    "KnowledgeBaseReadyEvent",
    "KnowledgeBaseReadyReference",
    "LlmCompletedEvent",
    "LlmCompletionReference",
    "ParsedDocumentReference",
    "PipelineProgressEvent",
    "RagCompletedEvent",
    "RagCompletionReference",
    "RiskScoredEvent",
    "RiskScoredReference",
    "TimeseriesAnalyzedEvent",
    "TimeseriesAnalyzedReference",
    "ValidatedDocumentReference",
    "VectorIndexedReference",
    "VectorsIndexedDocumentReference",
    "VectorsIndexedEvent",
]
