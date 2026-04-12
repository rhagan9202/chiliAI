"""Tests for SourceDocument lifecycle helpers."""

from __future__ import annotations

from ingestion.models import DocumentFormat, IngestionStatus, ParsedDocument, SourceDocument, SourceType
from ingestion.orchestrators.source_documents import (
    enrich_source_document,
    mark_failed,
    mark_parsed,
    mark_parsing,
)


def test_mark_parsing_returns_updated_copy() -> None:
    source = SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD)
    updated = mark_parsing(source)

    assert updated.status is IngestionStatus.PARSING
    assert source.status is IngestionStatus.PENDING


def test_mark_parsed_updates_processed_metadata() -> None:
    source = SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD)
    parsed = ParsedDocument(
        id="parsed-1",
        source_document_id="doc-1",
        text_content="hello",
        parser_name="text",
        parser_version="1.0",
    )

    updated = mark_parsed(source, parsed)
    assert updated.status is IngestionStatus.PARSED
    assert updated.processed_at == parsed.parsed_at
    assert updated.metadata["parser_name"] == "text"


def test_mark_failed_sets_error_detail() -> None:
    source = SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD)
    updated = mark_failed(source, "bad parse")

    assert updated.status is IngestionStatus.FAILED
    assert updated.error_detail == "bad parse"
    assert updated.processed_at is not None


def test_enrich_source_document_updates_non_null_fields_only() -> None:
    source = SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD)
    updated = enrich_source_document(
        source,
        document_format=DocumentFormat.CSV,
        filename="data.csv",
        size_bytes=128,
    )

    assert updated.document_format is DocumentFormat.CSV
    assert updated.filename == "data.csv"
    assert updated.size_bytes == 128
    assert updated.uri is None