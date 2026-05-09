"""Ingestion-internal transport and workflow models.

These models sit between parsers, chunkers, extractors, and downstream
validation/event publication. They intentionally remain domain-agnostic.
Validated runtime entities belong in ``shared.types``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

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
    FAILED = "failed"


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


class StructuredRecord(BaseModel):
    """A structured record extracted from a tabular or JSON source."""

    id: str
    fields: dict[str, object] = Field(default_factory=dict)
    row_number: int | None = Field(default=None, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Normalized parser output for one source document."""

    id: str
    source_document_id: str
    text_content: str | None = None
    records: list[StructuredRecord] = Field(default_factory=list)
    parser_name: str
    parser_version: str | None = None
    parsed_at: datetime = Field(default_factory=utc_now)
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
    evidence: list[ExtractionEvidence] = Field(default_factory=list)
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
    evidence: list[ExtractionEvidence] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Grouped extraction output for one ingestion unit."""

    id: str
    source_document_id: str
    parsed_document_id: str | None = None
    chunks: list[Chunk] = Field(default_factory=list)
    candidate_entities: list[CandidateEntity] = Field(default_factory=list)
    candidate_relationships: list[CandidateRelationship] = Field(default_factory=list)
    worker_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ValidationReport(BaseModel):
    """Validation outcome that converts candidates into shared runtime types."""

    id: str
    extraction_result_id: str
    source_document_id: str
    valid_entities: list[Entity] = Field(default_factory=list)
    valid_relationships: list[Relationship] = Field(default_factory=list)
    entity_errors: dict[str, list[str]] = Field(default_factory=dict)
    relationship_errors: dict[str, list[str]] = Field(default_factory=dict)
    validated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "CandidateEntity",
    "CandidateRelationship",
    "Chunk",
    "ChunkMetadata",
    "DocumentFormat",
    "ExtractionEvidence",
    "ExtractionResult",
    "IngestionStatus",
    "ParsedDocument",
    "SourceDocument",
    "SourceType",
    "StructuredRecord",
    "TextSpan",
    "ValidationReport",
]

