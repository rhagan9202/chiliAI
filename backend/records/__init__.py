"""Structured / tabular record ingestion module."""

from __future__ import annotations

from records.exceptions import (
    RecordFeedNotFoundError,
    RecordMappingError,
    RecordPersistenceError,
    RecordValidationError,
    RecordsError,
)
from records.models import RawRecord, RecordBatch, content_hash_for
from records.protocols import RecordsServiceProtocol
from records.service import RecordsService, create_records_service
from records.service_models import RecordIngestReceipt, RecordSubmission

__all__ = [
    "RawRecord",
    "RecordBatch",
    "RecordFeedNotFoundError",
    "RecordIngestReceipt",
    "RecordMappingError",
    "RecordPersistenceError",
    "RecordSubmission",
    "RecordValidationError",
    "RecordsError",
    "RecordsService",
    "RecordsServiceProtocol",
    "content_hash_for",
    "create_records_service",
]
