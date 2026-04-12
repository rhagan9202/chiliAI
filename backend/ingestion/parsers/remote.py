"""Remote HTTPS fetch support for parser dispatch."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

from ingestion.models import ParsedDocument, SourceDocument
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.exceptions import RemoteFetchError, UnsupportedFormatError
from ingestion.parsers.protocols import RemoteDocumentPayload, RemoteDocumentFetcher
from ingestion.parsers.registry import ParserRegistry
from ingestion.parsers.utils import infer_format_from_content_type, infer_format_from_filename


class HttpxRemoteDocumentFetcher(RemoteDocumentFetcher):
    """Fetch remote document bytes over HTTPS using httpx."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_bytes: int = 10_000_000,
        client: httpx.Client | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._client = client

    def fetch(self, source: SourceDocument) -> RemoteDocumentPayload:
        if not source.uri:
            raise RemoteFetchError("Source document does not have a remote URI.")
        parsed = urlparse(source.uri)
        if parsed.scheme.lower() != "https":
            raise RemoteFetchError("Remote document fetch only supports HTTPS URIs.")

        client = self._client or httpx.Client(timeout=self._timeout_seconds, follow_redirects=True)
        close_client = self._client is None
        try:
            response = client.get(source.uri)
            response.raise_for_status()
            declared_size = response.headers.get("content-length")
            if declared_size is not None and int(declared_size) > self._max_bytes:
                raise RemoteFetchError("Remote response exceeds configured size limit.")
            content = response.content
            if len(content) > self._max_bytes:
                raise RemoteFetchError("Remote response exceeds configured size limit.")

            filename = source.filename or PurePosixPath(urlparse(str(response.url)).path).name or None
            media_type = response.headers.get("content-type")
            inferred_format = infer_format_from_content_type(media_type) or infer_format_from_filename(filename)
            return RemoteDocumentPayload(
                content=content,
                final_url=str(response.url),
                media_type=media_type,
                filename=filename,
                size_bytes=len(content),
                inferred_format=inferred_format,
            )
        except httpx.HTTPError as exc:
            raise RemoteFetchError(f"Unable to fetch remote document: {exc}") from exc
        finally:
            if close_client:
                client.close()


def parse_remote_document(
    source: SourceDocument,
    registry: ParserRegistry,
    fetcher: RemoteDocumentFetcher,
) -> ParsedDocument:
    """Fetch a remote document and dispatch it through the parser orchestrator."""
    orchestrator = DocumentParsingOrchestrator(registry, fetcher=fetcher)
    try:
        return orchestrator.parse_source(source).parsed_document
    except UnsupportedFormatError as exc:
        raise UnsupportedFormatError("Unable to resolve remote document format.") from exc