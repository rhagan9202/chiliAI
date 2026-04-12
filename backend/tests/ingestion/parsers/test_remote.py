"""Tests for remote HTTPS fetching and remote parser dispatch."""

from __future__ import annotations

import httpx
import pytest

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.parsers.exceptions import RemoteFetchError, UnsupportedFormatError
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher, parse_remote_document


def test_remote_fetcher_fetches_and_infers_format_from_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://example.com/data.csv")
        return httpx.Response(
            200,
            headers={"content-type": "text/csv", "content-length": "18"},
            content=b"id,name\n1,Alice\n",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    fetcher = HttpxRemoteDocumentFetcher(client=client)
    payload = fetcher.fetch(
        SourceDocument(
            id="remote-1",
            source_type=SourceType.API_PUSH,
            uri="https://example.com/data.csv",
        )
    )

    assert payload.inferred_format is DocumentFormat.CSV
    assert payload.size_bytes == 16


def test_remote_fetcher_rejects_non_https() -> None:
    fetcher = HttpxRemoteDocumentFetcher(client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    with pytest.raises(RemoteFetchError, match="HTTPS"):
        fetcher.fetch(
            SourceDocument(
                id="remote-1",
                source_type=SourceType.API_PUSH,
                uri="http://example.com/data.csv",
            )
        )


def test_parse_remote_document_dispatches_by_inferred_format() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"claim_id": "C-1"}',
        )

    registry = create_default_registry()
    fetcher = HttpxRemoteDocumentFetcher(client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    parsed = parse_remote_document(
        SourceDocument(
            id="remote-2",
            source_type=SourceType.API_PUSH,
            uri="https://example.com/resource",
        ),
        registry,
        fetcher,
    )

    assert parsed.parser_name == "json"
    assert parsed.records[0].fields["claim_id"] == "C-1"


def test_parse_remote_document_rejects_unknown_remote_format() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"binary")

    registry = create_default_registry()
    fetcher = HttpxRemoteDocumentFetcher(client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    with pytest.raises(UnsupportedFormatError, match="resolve remote document format"):
        parse_remote_document(
            SourceDocument(
                id="remote-3",
                source_type=SourceType.API_PUSH,
                uri="https://example.com/blob",
            ),
            registry,
            fetcher,
        )