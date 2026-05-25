"""Service-boundary models for the records ingestion API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from shared.utils import utc_now


class RecordSubmission(BaseModel):
    """A batch of rows submitted to a single feed."""

    feed_name: str
    rows: list[dict[str, object]]
    source_type: Literal["file_upload", "api_push"]
    source_ref: str | None = None


class RecordIngestReceipt(BaseModel):
    """Receipt returned after a record submission is registered."""

    knowledge_base_id: str
    feed_name: str
    record_type: str
    correlation_id: str
    accepted_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "RecordIngestReceipt",
    "RecordSubmission",
]
