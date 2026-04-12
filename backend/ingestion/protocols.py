"""Ingestion service protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from events.types import DocumentsUploadedEvent
from ingestion.orchestrators.protocols import DocumentParseFailure, ParseResult
from ingestion.service_models import DocumentReceipt, DocumentSubmission, IngestionTask


@runtime_checkable
class IngestionServiceProtocol(Protocol):
    """Service boundary consumed by API and worker code."""

    def register_documents(
        self,
        knowledge_base_id: str,
        submissions: list[DocumentSubmission],
    ) -> list[DocumentReceipt]: ...

    def ingest_task(self, task: IngestionTask) -> ParseResult | DocumentParseFailure: ...

    def process_documents_uploaded(
        self,
        event: DocumentsUploadedEvent,
    ) -> list[ParseResult | DocumentParseFailure]: ...