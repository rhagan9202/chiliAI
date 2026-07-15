"""Ingestion-internal transport and workflow models.

These models sit between parsers, chunkers, extractors, and downstream
validation/event publication. They intentionally remain domain-agnostic.
Validated runtime entities belong in ``shared.types``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from shared.provenance import SOURCE_KIND_DOCUMENT
from shared.types import Entity, Relationship
from shared.utils import utc_now


class SourceType(str, Enum):
    """Supported ingestion entry points."""

    FILE_UPLOAD = "file_upload"
    API_PUSH = "api_push"
    BATCH_LOAD = "batch_load"


class DocumentFormat(str, Enum):
    """Supported source document formats."""

    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    TXT = "txt"
    CSV = "csv"
    JSON = "json"
    HTML = "html"


class IngestionStatus(str, Enum):
    """Lifecycle states for a source document during ingestion."""

    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKED = "chunked"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    EXTRACTED_EMPTY = "extracted_empty"
    FAILED = "failed"


# Monotonic ordering for the durable per-document status projection (BL-041).
# A transition only changes the stored status when its rank is strictly
# greater, so a stale `parsing` arriving after `failed` is ignored and event
# redelivery is a no-op. Gaps of 10 leave room for future stages.
STATUS_RANK: dict[IngestionStatus, int] = {
    IngestionStatus.PENDING: 0,
    IngestionStatus.PARSING: 10,
    IngestionStatus.PARSED: 20,
    IngestionStatus.CHUNKED: 30,
    IngestionStatus.EXTRACTED: 40,
    IngestionStatus.VALIDATED: 50,
    IngestionStatus.EXTRACTED_EMPTY: 60,
    IngestionStatus.FAILED: 70,
}


class SourceDocument(BaseModel):
    """A single uploaded or pushed source unit awaiting ingestion."""

    id: str
    source_type: SourceType
    document_format: DocumentFormat | None = None
    knowledge_base_id: str | None = None
    filename: str | None = None
    uri: str | None = None
    media_type: str | None = None
    checksum: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    status: IngestionStatus = IngestionStatus.PENDING
    uploaded_at: datetime = Field(default_factory=utc_now)
    processed_at: datetime | None = None
    error_detail: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentStatusTransition(BaseModel):
    """One projected status observation for a source document.

    ``None`` count/reason fields mean "leave the stored value unchanged";
    populated fields carry absolute values from the validation report and
    overwrite (idempotent on redelivery).
    """

    knowledge_base_id: str
    source_document_id: str
    status: IngestionStatus
    error_message: str | None = None
    dropped_entity_count: int | None = Field(default=None, ge=0)
    dropped_relationship_count: int | None = Field(default=None, ge=0)
    sample_reasons: list[str] | None = None
    occurred_at: datetime = Field(default_factory=utc_now)


class SourceDocumentStatusRecord(BaseModel):
    """Durable current-status projection row for a source document."""

    knowledge_base_id: str
    source_document_id: str
    current_status: IngestionStatus
    status_rank: int = Field(ge=0)
    last_error: str | None = None
    dropped_entity_count: int = Field(default=0, ge=0)
    dropped_relationship_count: int = Field(default=0, ge=0)
    sample_reasons: list[str] = Field(default_factory=list)
    first_event_at: datetime
    updated_at: datetime


class StructuredRecord(BaseModel):
    """A structured record extracted from a tabular or JSON source."""

    id: str
    fields: dict[str, object] = Field(default_factory=dict)
    row_number: int | None = Field(default=None, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class ParserWarning(BaseModel):
    """A typed, non-fatal diagnostic surfaced by a parser.

    Carries a stable ``code`` so the UI can group and count warnings by category
    instead of parsing free-form ``parser_metadata``. Location fields are optional
    and populated only when the warning is anchored to a specific row/page/column.
    """

    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    row_index: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, gt=0)
    column_name: str | None = None


class ParsedDocument(BaseModel):
    """Normalized parser output for one source document."""

    id: str
    source_document_id: str
    text_content: str | None = None
    records: list[StructuredRecord] = Field(
        default_factory=lambda: cast(list[StructuredRecord], [])
    )
    parser_name: str
    parser_version: str | None = None
    parsed_at: datetime = Field(default_factory=utc_now)
    warnings: list[ParserWarning] = Field(
        default_factory=lambda: cast(list[ParserWarning], [])
    )
    parser_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_content(self) -> ParsedDocument:
        has_text = self.text_content is not None and self.text_content.strip() != ""
        if has_text or self.records:
            return self
        raise ValueError(
            "ParsedDocument requires non-empty text_content or at least one structured record."
        )


class ChunkMetadata(BaseModel):
    """Typed provenance for a chunk generated from a parsed document."""

    source_document_id: str
    chunk_index: int = Field(ge=0)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, gt=0)
    section_heading: str | None = None
    source_kind: str = SOURCE_KIND_DOCUMENT
    parser_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_offsets(self) -> ChunkMetadata:
        if self.start_offset is not None and self.end_offset is not None:
            if self.end_offset < self.start_offset:
                raise ValueError("ChunkMetadata end_offset must be >= start_offset.")
        return self


class Chunk(BaseModel):
    """A typed chunk of parsed content passed to extraction."""

    id: str
    content: str
    metadata: ChunkMetadata
    tokens_estimate: int | None = Field(default=None, ge=0)
    language: str | None = None


class TextSpan(BaseModel):
    """A precise span of source text used as extraction evidence."""

    text: str
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_offsets(self) -> TextSpan:
        if self.start_offset is not None and self.end_offset is not None:
            if self.end_offset < self.start_offset:
                raise ValueError("TextSpan end_offset must be >= start_offset.")
        return self


class ExtractionEvidence(BaseModel):
    """Provenance attached to a candidate entity or relationship."""

    chunk_id: str
    span: TextSpan | None = None
    quote: str | None = None
    rationale: str | None = None


class CandidateEntity(BaseModel):
    """Pre-validation entity candidate emitted by the extractor."""

    id: str
    source_document_id: str
    chunk_id: str
    type: str
    properties: dict[str, object] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: str
    evidence: list[ExtractionEvidence] = Field(
        default_factory=lambda: cast(list[ExtractionEvidence], [])
    )
    metadata: dict[str, object] = Field(default_factory=dict)


class CandidateRelationship(BaseModel):
    """Pre-validation relationship candidate emitted by the extractor."""

    id: str
    source_document_id: str
    chunk_id: str
    type: str
    source_candidate_id: str
    target_candidate_id: str
    properties: dict[str, object] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: str
    evidence: list[ExtractionEvidence] = Field(
        default_factory=lambda: cast(list[ExtractionEvidence], [])
    )
    metadata: dict[str, object] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Grouped extraction output for one ingestion unit."""

    id: str
    source_document_id: str
    parsed_document_id: str | None = None
    chunks: list[Chunk] = Field(default_factory=lambda: cast(list[Chunk], []))
    candidate_entities: list[CandidateEntity] = Field(
        default_factory=lambda: cast(list[CandidateEntity], [])
    )
    candidate_relationships: list[CandidateRelationship] = Field(
        default_factory=lambda: cast(list[CandidateRelationship], [])
    )
    worker_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ValidationReport(BaseModel):
    """Validation outcome that converts candidates into shared runtime types."""

    id: str
    extraction_result_id: str
    source_document_id: str
    valid_entities: list[Entity] = Field(default_factory=lambda: cast(list[Entity], []))
    valid_relationships: list[Relationship] = Field(
        default_factory=lambda: cast(list[Relationship], [])
    )
    entity_errors: dict[str, list[str]] = Field(default_factory=dict)
    relationship_errors: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "CandidateEntity",
    "CandidateRelationship",
    "Chunk",
    "ChunkMetadata",
    "DocumentFormat",
    "DocumentStatusTransition",
    "ExtractionEvidence",
    "ExtractionResult",
    "IngestionStatus",
    "ParsedDocument",
    "ParserWarning",
    "SourceDocument",
    "SourceDocumentStatusRecord",
    "SourceType",
    "STATUS_RANK",
    "StructuredRecord",
    "TextSpan",
    "ValidationReport",
]
