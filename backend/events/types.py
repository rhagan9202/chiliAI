"""Event payload types for the staged backend workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventBase(BaseModel):
    """Base event envelope."""

    event_type: str
    occurred_at: datetime = Field(default_factory=_utc_now)


class KnowledgeBaseCreatedEvent(EventBase):
    event_type: Literal["kb.create"] = "kb.create"
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


class VectorIndexedReference(BaseModel):
    knowledge_base_id: str
    record_id: str
    content_id: str
    dimension: int = Field(gt=0)


class VectorsIndexedEvent(EventBase):
    event_type: Literal["vectors.indexed"] = "vectors.indexed"
    records: list[VectorIndexedReference]


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
    | DocumentsUploadedEvent
    | DocumentsParsedEvent
    | DocumentsChunkedEvent
    | EntitiesExtractedEvent
    | EntitiesValidatedEvent
    | GraphUpdatedEvent
    | VectorsIndexedEvent
    | LlmCompletedEvent
    | EmbeddingsGeneratedEvent
    | DocumentsFailedEvent
    | ClaimsReceivedEvent
    | ClaimsIngestedEvent
)
