"""Durable dead-letter-queue record models (BL-023, events.10)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from shared.utils import utc_now

DlqRecordStatus = Literal["pending", "replayed", "discarded"]


class DlqRecord(BaseModel):
    """One dead-lettered event captured at retry exhaustion."""

    dlq_id: str
    event_type: str
    correlation_id: str
    payload: dict[str, str]
    error_message: str
    error_traceback: str
    retry_count: int
    failed_at: datetime
    status: DlqRecordStatus = "pending"
    replayed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DlqRecordListResponse(BaseModel):
    """Paginated DLQ listing for the operator API."""

    items: list[DlqRecord]
    total: int


__all__ = ["DlqRecord", "DlqRecordListResponse", "DlqRecordStatus"]
