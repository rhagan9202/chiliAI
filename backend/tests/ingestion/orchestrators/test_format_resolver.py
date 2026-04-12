"""Tests for parser orchestration format resolution."""

from __future__ import annotations

import pytest

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.orchestrators.format_resolver import DefaultFormatResolver
from ingestion.parsers.exceptions import UnsupportedFormatError


def test_resolver_prefers_explicit_format() -> None:
    resolver = DefaultFormatResolver()
    source = SourceDocument(
        id="doc-1",
        source_type=SourceType.FILE_UPLOAD,
        document_format=DocumentFormat.JSON,
        filename="data.csv",
    )

    assert resolver.resolve(source, content_type="text/csv") is DocumentFormat.JSON


def test_resolver_uses_content_type_before_filename() -> None:
    resolver = DefaultFormatResolver()
    source = SourceDocument(
        id="doc-1",
        source_type=SourceType.API_PUSH,
        filename="payload.txt",
    )

    assert resolver.resolve(source, content_type="application/json") is DocumentFormat.JSON


def test_resolver_falls_back_to_filename_then_uri() -> None:
    resolver = DefaultFormatResolver()
    source_from_filename = SourceDocument(
        id="doc-1",
        source_type=SourceType.FILE_UPLOAD,
        filename="report.pdf",
    )
    source_from_uri = SourceDocument(
        id="doc-2",
        source_type=SourceType.API_PUSH,
        uri="https://example.com/export.xlsx",
    )

    assert resolver.resolve(source_from_filename) is DocumentFormat.PDF
    assert resolver.resolve(source_from_uri) is DocumentFormat.XLSX


def test_resolver_rejects_unknown_inputs() -> None:
    resolver = DefaultFormatResolver()
    source = SourceDocument(id="doc-1", source_type=SourceType.BATCH_LOAD)

    with pytest.raises(UnsupportedFormatError, match="resolve document format"):
        resolver.resolve(source)