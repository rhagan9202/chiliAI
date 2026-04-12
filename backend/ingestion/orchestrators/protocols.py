"""Protocols and result models for parser orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument


class ParseResult(BaseModel):
    """Successful parser orchestration result."""

    source_document: SourceDocument
    parsed_document: ParsedDocument


class DocumentParseFailure(BaseModel):
    """A structured parse failure for safe or batch orchestration flows."""

    source_document: SourceDocument
    error_type: str
    error_message: str


class BatchParseResult(BaseModel):
    """Aggregated result for batch parsing helpers."""

    successes: list[ParseResult] = Field(default_factory=list)
    failures: list[DocumentParseFailure] = Field(default_factory=list)


@runtime_checkable
class FormatResolver(Protocol):
    """Resolve a document format from source and transport metadata."""

    def resolve(
        self,
        source: SourceDocument,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        uri: str | None = None,
    ) -> DocumentFormat: ...


@runtime_checkable
class ParserOrchestrator(Protocol):
    """Coordinate parsing for local bytes or remote sources."""

    def parse_content(
        self,
        source: SourceDocument,
        content: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        uri: str | None = None,
    ) -> ParseResult: ...

    def parse_source(self, source: SourceDocument) -> ParseResult: ...