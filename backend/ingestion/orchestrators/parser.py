"""Single-document parser orchestration helpers."""

from __future__ import annotations

from ingestion.models import SourceDocument
from ingestion.orchestrators.format_resolver import DefaultFormatResolver
from ingestion.orchestrators.protocols import (
    DocumentParseFailure,
    FormatResolver,
    ParseResult,
)
from ingestion.orchestrators.source_documents import (
    enrich_source_document,
    mark_failed,
    mark_parsed,
    mark_parsing,
)
from ingestion.parsers.exceptions import ParserError, RemoteFetchError
from ingestion.parsers.protocols import RemoteDocumentFetcher
from ingestion.parsers.registry import ParserRegistry


class DocumentParsingOrchestrator:
    """Coordinate local and remote parsing with consistent lifecycle updates."""

    def __init__(
        self,
        registry: ParserRegistry,
        *,
        fetcher: RemoteDocumentFetcher | None = None,
        format_resolver: FormatResolver | None = None,
    ) -> None:
        self._registry = registry
        self._fetcher = fetcher
        self._format_resolver = format_resolver or DefaultFormatResolver()

    def parse_content(
        self,
        source: SourceDocument,
        content: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        uri: str | None = None,
    ) -> ParseResult:
        parsing_source = mark_parsing(source)
        resolved_format = self._format_resolver.resolve(
            parsing_source,
            content_type=content_type,
            filename=filename,
            uri=uri,
        )
        prepared_source = enrich_source_document(
            parsing_source,
            document_format=resolved_format,
            filename=filename,
            media_type=content_type,
            size_bytes=len(content),
            uri=uri,
        )
        parsed_document = self._registry.parse(prepared_source, content)
        return ParseResult(
            source_document=mark_parsed(prepared_source, parsed_document),
            parsed_document=parsed_document,
        )

    def safe_parse_content(
        self,
        source: SourceDocument,
        content: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        uri: str | None = None,
    ) -> ParseResult | DocumentParseFailure:
        try:
            return self.parse_content(
                source,
                content,
                content_type=content_type,
                filename=filename,
                uri=uri,
            )
        except ParserError as exc:
            failed_source = mark_failed(mark_parsing(source), str(exc))
            return DocumentParseFailure(
                source_document=failed_source,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    def parse_source(self, source: SourceDocument) -> ParseResult:
        if self._fetcher is None:
            raise RemoteFetchError("A remote document fetcher is required for URI-based parsing.")
        payload = self._fetcher.fetch(source)
        return self.parse_content(
            source,
            payload.content,
            content_type=payload.media_type,
            filename=payload.filename,
            uri=payload.final_url,
        )

    def safe_parse_source(self, source: SourceDocument) -> ParseResult | DocumentParseFailure:
        try:
            return self.parse_source(source)
        except (ParserError, RemoteFetchError) as exc:
            failed_source = mark_failed(mark_parsing(source), str(exc))
            return DocumentParseFailure(
                source_document=failed_source,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )