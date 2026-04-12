"""Service-boundary models for ingestion registration and execution."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from ingestion.models import DocumentFormat, IngestionStatus, SourceDocument, SourceType


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentSubmission(BaseModel):
    """A document submitted to the ingestion service."""

    filename: str | None = None
    content: bytes | None = None
    content_type: str | None = None
    uri: str | None = None
    document_format: DocumentFormat | None = None
    source_type: SourceType | None = None

    @model_validator(mode="after")
    def _validate_source(self) -> DocumentSubmission:
        if self.content is not None or self.uri is not None:
            return self
        raise ValueError("DocumentSubmission requires content bytes or a remote URI.")


class DocumentReceipt(BaseModel):
    """Receipt returned after document registration."""

    knowledge_base_id: str
    source_document_id: str
    filename: str | None = None
    status: IngestionStatus
    storage_key: str | None = None
    uri: str | None = None
    document_format: DocumentFormat | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class IngestionTask(BaseModel):
    """A worker-consumable ingestion task."""

    knowledge_base_id: str
    source_document: SourceDocument
    storage_key: str | None = None
    content_type: str | None = None