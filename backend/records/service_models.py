"""Service-boundary models for the records ingestion API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from records.models import RejectedRow
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
    duplicate: bool = False
    duplicate_count: int = Field(default=0, ge=0)
    # Rows whose record_id already existed (any content) and were silently
    # dropped by the store's per-row dedup during persist(). Distinct from
    # `duplicate`/`duplicate_count`, which flag a whole batch that is an
    # identical resubmission (no-op, no persist at all).
    suppressed_existing_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    rejected: list[RejectedRow] = Field(
        default_factory=lambda: cast(list[RejectedRow], [])
    )
    created_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "RecordIngestReceipt",
    "RecordSubmission",
]
