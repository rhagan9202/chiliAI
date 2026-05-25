"""Tests for batch parser orchestration."""

from __future__ import annotations

import pytest

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.orchestrators.batch import BatchDocumentParsingOrchestrator, BatchParseItem
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.protocols import RemoteDocumentPayload
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


def test_batch_parse_item_requires_content_or_uri() -> None:
    with pytest.raises(ValueError, match="content bytes or a source URI"):
        BatchParseItem(
            source_document=SourceDocument(
                id="doc-1",
                source_type=SourceType.FILE_UPLOAD,
            )
        )


class _RecordingFetcher:
    def __init__(self) -> None:
        self.seen_uri: str | None = None

    def fetch(self, source: SourceDocument) -> RemoteDocumentPayload:
        self.seen_uri = source.uri
        return RemoteDocumentPayload(
            content=b'{"claim_id": "remote"}',
            final_url=source.uri or "",
            media_type="application/json",
            size_bytes=22,
            inferred_format=DocumentFormat.JSON,
        )


def test_batch_parser_uses_item_uri_override_for_remote_source() -> None:
    fetcher = _RecordingFetcher()
    batch = BatchDocumentParsingOrchestrator(
        DocumentParsingOrchestrator(create_default_registry(), fetcher=fetcher)
    )

    result = batch.parse(
        [
            BatchParseItem(
                source_document=SourceDocument(
                    id="doc-remote",
                    source_type=SourceType.API_PUSH,
                    uri="https://example.com/original.json",
                ),
                uri="https://example.com/override.json",
            )
        ]
    )

    assert fetcher.seen_uri == "https://example.com/override.json"
    assert result.successes[0].parsed_document.records[0].fields["claim_id"] == "remote"
