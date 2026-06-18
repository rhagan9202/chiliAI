"""Tests for single-document parser orchestration."""

from __future__ import annotations

import httpx
import pytest

from ingestion.models import DocumentFormat, IngestionStatus, ParsedDocument, SourceDocument, SourceType
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.orchestrators.protocols import DocumentParseFailure
from ingestion.parsers.exceptions import RemoteFetchError
from ingestion.parsers.protocols import RemoteDocumentPayload
from ingestion.parsers.registry import ParserRegistry, create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher


class _RaisingParser:
    """Parser that raises a non-ParserError mid-parse (e.g. lazy iteration)."""

    name = "raising"
    version = "1.0"
    supported_formats = (DocumentFormat.TXT,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        raise RuntimeError("page extraction blew up")


def test_parse_content_updates_status_and_metadata() -> None:
    orchestrator = DocumentParsingOrchestrator(create_default_registry())
    result = orchestrator.parse_content(
        SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD, filename="data.json"),
        b'{"claim_id": "42"}',
        content_type="application/json",
    )

    assert result.source_document.status is IngestionStatus.PARSED
    assert result.source_document.document_format is DocumentFormat.JSON
    assert result.source_document.metadata["parser_name"] == "json"
    assert result.parsed_document.records[0].fields["claim_id"] == "42"


def test_safe_parse_content_returns_failure_model() -> None:
    orchestrator = DocumentParsingOrchestrator(create_default_registry())
    outcome = orchestrator.safe_parse_content(
        SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD),
        b"binary",
    )

    assert isinstance(outcome, DocumentParseFailure)
    assert outcome.source_document.status is IngestionStatus.FAILED
    assert outcome.error_type == "UnsupportedFormatError"


def test_parse_source_fetches_remote_document() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/csv"},
            content=b"claim_id,amount\n1,100\n",
        )

    fetcher = HttpxRemoteDocumentFetcher(client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    orchestrator = DocumentParsingOrchestrator(create_default_registry(), fetcher=fetcher)
    result = orchestrator.parse_source(
        SourceDocument(id="doc-1", source_type=SourceType.API_PUSH, uri="https://example.com/data")
    )

    assert result.source_document.status is IngestionStatus.PARSED
    assert result.source_document.document_format is DocumentFormat.CSV
    assert result.parsed_document.records[0].fields["claim_id"] == "1"


def test_parse_source_requires_fetcher() -> None:
    orchestrator = DocumentParsingOrchestrator(create_default_registry())
    with pytest.raises(RemoteFetchError, match="fetcher"):
        orchestrator.parse_source(
            SourceDocument(id="doc-1", source_type=SourceType.API_PUSH, uri="https://example.com/data")
        )


def test_safe_parse_source_reports_remote_failure() -> None:
    orchestrator = DocumentParsingOrchestrator(create_default_registry())
    outcome = orchestrator.safe_parse_source(
        SourceDocument(id="doc-1", source_type=SourceType.API_PUSH, uri="https://example.com/data")
    )

    assert isinstance(outcome, DocumentParseFailure)
    assert outcome.source_document.status is IngestionStatus.FAILED
    assert outcome.error_type == "RemoteFetchError"


def test_safe_parse_content_wraps_unexpected_non_parser_error() -> None:
    orchestrator = DocumentParsingOrchestrator(ParserRegistry(parsers=[_RaisingParser()]))
    outcome = orchestrator.safe_parse_content(
        SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD, filename="x.txt"),
        b"some content",
        content_type="text/plain",
        filename="x.txt",
    )

    assert isinstance(outcome, DocumentParseFailure)
    assert outcome.source_document.status is IngestionStatus.FAILED
    assert outcome.error_type == "RuntimeError"
    assert "page extraction blew up" in outcome.error_message


class _RaisingFetcher:
    """Remote fetcher that raises a non-ParserError."""

    def fetch(self, source: SourceDocument) -> RemoteDocumentPayload:
        raise RuntimeError("network exploded")


def test_safe_parse_source_wraps_unexpected_non_parser_error() -> None:
    orchestrator = DocumentParsingOrchestrator(
        create_default_registry(),
        fetcher=_RaisingFetcher(),
    )
    outcome = orchestrator.safe_parse_source(
        SourceDocument(id="doc-1", source_type=SourceType.API_PUSH, uri="https://example.com/data")
    )

    assert isinstance(outcome, DocumentParseFailure)
    assert outcome.source_document.status is IngestionStatus.FAILED
    assert outcome.error_type == "RuntimeError"
    assert "network exploded" in outcome.error_message


def test_safe_parse_content_wraps_empty_content_validation_error() -> None:
    orchestrator = DocumentParsingOrchestrator(create_default_registry())
    outcome = orchestrator.safe_parse_content(
        SourceDocument(id="doc-1", source_type=SourceType.FILE_UPLOAD, filename="empty.txt"),
        b"",
        content_type="text/plain",
        filename="empty.txt",
    )

    assert isinstance(outcome, DocumentParseFailure)
    assert outcome.source_document.status is IngestionStatus.FAILED
    assert outcome.error_type == "ValidationError"