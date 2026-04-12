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
    event_type: Literal["docs.uploaded"] = "docs.uploaded"
    documents: list[DocumentReference]


class ParsedDocumentReference(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    parser_name: str
    parser_version: str | None = None
    document_format: str | None = None
    storage_key: str | None = None


class DocumentsParsedEvent(EventBase):
    event_type: Literal["documents.parsed"] = "documents.parsed"
    documents: list[ParsedDocumentReference]


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
    | DocumentsFailedEvent
    | ClaimsReceivedEvent
    | ClaimsIngestedEvent
)
