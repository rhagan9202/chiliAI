"""Tests for parser registry and exports."""

from __future__ import annotations

import pytest

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.parsers import create_default_registry
from ingestion.parsers.exceptions import UnsupportedFormatError
from ingestion.parsers.registry import ParserRegistry
from ingestion.parsers.txt import TextParser


def test_default_registry_dispatches_to_text_parser() -> None:
    registry = create_default_registry()
    parsed = registry.parse(
        SourceDocument(
            id="doc-1",
            source_type=SourceType.FILE_UPLOAD,
            document_format=DocumentFormat.TXT,
        ),
        b"hello",
    )

    assert parsed.parser_name == "text"
    assert parsed.text_content == "hello"


def test_registry_rejects_missing_format() -> None:
    registry = ParserRegistry([TextParser()])
    with pytest.raises(UnsupportedFormatError, match="not resolved"):
        registry.parse(SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD), b"hello")


def test_registry_rejects_unregistered_format() -> None:
    registry = ParserRegistry([TextParser()])
    with pytest.raises(UnsupportedFormatError, match="No parser registered"):
        registry.get_parser(DocumentFormat.PDF)