"""Models for the knowledgebases module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import utc_now

__all__ = ["MAX_DOCUMENT_WARNING_REASONS", "DocumentRecord"]

# Bounded sample of human-readable warning reasons kept per document; counts
# are exact, reasons are a sample (mirrors the extraction-warning event cap).
MAX_DOCUMENT_WARNING_REASONS = 10


class DocumentRecord(BaseModel):
    """Metadata recorded for a registered document inside a knowledge base."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str = "registered"
    storage_key: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    # Ingestion diagnostics: parse + extraction/validation warnings accumulated
    # by the worker so the UI can explain degraded or empty ingestion results.
    warning_count: int = Field(default=0, ge=0)
    warning_reasons: list[str] = Field(default_factory=list)
