"""Service-level protocols for the records module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from records.service_models import RecordIngestReceipt, RecordSubmission


@runtime_checkable
class RecordsServiceProtocol(Protocol):
    """Service boundary for structured-record ingestion consumed by the API."""

    def register_records(
        self, knowledge_base_id: str, submission: RecordSubmission
    ) -> RecordIngestReceipt: ...


__all__ = [
    "RecordsServiceProtocol",
]
