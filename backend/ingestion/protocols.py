"""Ingestion service protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from events.types import DocumentsUploadedEvent
from ingestion.chunker import ChunkingResult
from ingestion.models import ExtractionResult, ParsedDocument, ValidationReport
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


@runtime_checkable
class DocumentChunkerProtocol(Protocol):
    """Chunk parsed documents into extraction-ready units."""

    def chunk_document(
        self,
        parsed_document: ParsedDocument,
        source_document_id: str,
    ) -> ChunkingResult: ...


@runtime_checkable
class DocumentExtractorProtocol(Protocol):
    """Extract entity candidates from chunked documents."""

    def extract_document(self, chunking_result: ChunkingResult) -> ExtractionResult: ...


@runtime_checkable
class DocumentValidatorProtocol(Protocol):
    """Validate extracted candidates against config-defined runtime schemas."""

    def validate_extraction(self, extraction_result: ExtractionResult) -> ValidationReport: ...