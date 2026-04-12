"""Tests for batch parser orchestration."""

from __future__ import annotations

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.orchestrators.batch import BatchDocumentParsingOrchestrator, BatchParseItem
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry


def test_batch_parser_collects_partial_failures() -> None:
    batch = BatchDocumentParsingOrchestrator(DocumentParsingOrchestrator(create_default_registry()))
    result = batch.parse(
        [
            BatchParseItem(
                source_document=SourceDocument(
                    id="doc-1",
                    source_type=SourceType.FILE_UPLOAD,
                    document_format=DocumentFormat.JSON,
                ),
                content=b'{"claim_id": "42"}',
            ),
            BatchParseItem(
                source_document=SourceDocument(
                    id="doc-2",
                    source_type=SourceType.FILE_UPLOAD,
                ),
                content=b"binary",
            ),
        ]
    )

    assert len(result.successes) == 1
    assert len(result.failures) == 1
    assert result.successes[0].parsed_document.records[0].fields["claim_id"] == "42"
    assert result.failures[0].error_type == "UnsupportedFormatError"