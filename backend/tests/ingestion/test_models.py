"""Tests for ingestion models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ingestion.models import (
    CandidateEntity,
    CandidateRelationship,
    Chunk,
    ChunkMetadata,
    DocumentFormat,
    ExtractionEvidence,
    ExtractionResult,
    IngestionStatus,
    ParsedDocument,
    SourceDocument,
    SourceType,
    StructuredRecord,
    TextSpan,
    ValidationReport,
)
from shared.types import Entity, Relationship


def test_source_document_defaults() -> None:
    document = SourceDocument(
        id="doc-1",
        source_type=SourceType.FILE_UPLOAD,
        document_format=DocumentFormat.PDF,
        filename="policy.pdf",
    )

    assert document.status is IngestionStatus.PENDING
    assert document.metadata == {}
    assert document.uploaded_at.tzinfo is timezone.utc


def test_parsed_document_accepts_text_content() -> None:
    parsed = ParsedDocument(
        id="parsed-1",
        source_document_id="doc-1",
        text_content="Normalized text",
        parser_name="pdf_parser",
    )

    assert parsed.text_content == "Normalized text"
    assert parsed.records == []


def test_parsed_document_accepts_structured_records_without_text() -> None:
    parsed = ParsedDocument(
        id="parsed-1",
        source_document_id="doc-1",
        parser_name="csv_parser",
        records=[StructuredRecord(id="row-1", fields={"claim_id": "123"})],
    )

    assert parsed.text_content is None
    assert parsed.records[0].fields["claim_id"] == "123"


def test_parsed_document_requires_text_or_records() -> None:
    with pytest.raises(ValidationError, match="ParsedDocument requires"):
        ParsedDocument(
            id="parsed-1",
            source_document_id="doc-1",
            parser_name="empty_parser",
        )


def test_chunk_metadata_lineage_is_typed() -> None:
    metadata = ChunkMetadata(
        source_document_id="doc-1",
        chunk_index=2,
        start_offset=100,
        end_offset=180,
        page_number=3,
        section_heading="Claims Overview",
    )
    chunk = Chunk(id="chunk-1", content="sample", metadata=metadata, tokens_estimate=15)

    assert chunk.metadata.source_document_id == "doc-1"
    assert chunk.metadata.chunk_index == 2
    assert chunk.tokens_estimate == 15


def test_chunk_metadata_rejects_inverted_offsets() -> None:
    with pytest.raises(ValidationError, match="end_offset"):
        ChunkMetadata(
            source_document_id="doc-1",
            chunk_index=0,
            start_offset=50,
            end_offset=10,
        )


def test_text_span_rejects_inverted_offsets() -> None:
    with pytest.raises(ValidationError, match="TextSpan end_offset"):
        TextSpan(text="abc", start_offset=5, end_offset=2)


def test_candidate_entity_serializes_evidence() -> None:
    entity = CandidateEntity(
        id="ce-1",
        source_document_id="doc-1",
        chunk_id="chunk-1",
        type="provider",
        properties={"npi": "1234567890"},
        confidence=0.92,
        extraction_method="llm_prompt_v1",
        evidence=[
            ExtractionEvidence(
                chunk_id="chunk-1",
                span=TextSpan(text="NPI 1234567890", start_offset=12, end_offset=26),
                quote="NPI 1234567890",
                rationale="Detected labeled identifier.",
            )
        ],
    )

    dumped = entity.model_dump()
    assert dumped["evidence"][0]["quote"] == "NPI 1234567890"
    assert dumped["type"] == "provider"


def test_candidate_relationship_defaults() -> None:
    relationship = CandidateRelationship(
        id="cr-1",
        source_document_id="doc-1",
        chunk_id="chunk-1",
        type="submitted_by",
        source_candidate_id="ce-claim",
        target_candidate_id="ce-provider",
        confidence=0.81,
        extraction_method="pattern_v2",
    )

    assert relationship.properties == {}
    assert relationship.evidence == []


def test_extraction_result_groups_chunks_and_candidates() -> None:
    chunk = Chunk(
        id="chunk-1",
        content="Claim 42 submitted by provider.",
        metadata=ChunkMetadata(source_document_id="doc-1", chunk_index=0),
    )
    candidate = CandidateEntity(
        id="ce-1",
        source_document_id="doc-1",
        chunk_id="chunk-1",
        type="claim",
        properties={"claim_id": "42"},
        confidence=0.88,
        extraction_method="llm_prompt_v1",
    )

    result = ExtractionResult(
        id="er-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        chunks=[chunk],
        candidate_entities=[candidate],
        warnings=["Low OCR confidence on page 2."],
    )

    assert result.chunks[0].metadata.source_document_id == "doc-1"
    assert result.candidate_entities[0].type == "claim"
    assert result.warnings == ["Low OCR confidence on page 2."]


def test_validation_report_wraps_shared_runtime_types() -> None:
    now = datetime.now(timezone.utc)
    report = ValidationReport(
        id="vr-1",
        extraction_result_id="er-1",
        source_document_id="doc-1",
        valid_entities=[
            Entity(id="entity-1", type="provider", properties={"npi": "123"})
        ],
        valid_relationships=[
            Relationship(
                id="rel-1",
                type="submitted_by",
                source_id="claim-1",
                target_id="provider-1",
            )
        ],
        entity_errors={"ce-bad": ["Unknown entity type 'providerx'."]},
        validated_at=now,
    )

    assert report.valid_entities[0].type == "provider"
    assert report.valid_relationships[0].type == "submitted_by"
    assert report.entity_errors["ce-bad"] == ["Unknown entity type 'providerx'."]


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        CandidateEntity(
            id="ce-1",
            source_document_id="doc-1",
            chunk_id="chunk-1",
            type="provider",
            confidence=1.5,
            extraction_method="llm_prompt_v1",
        )