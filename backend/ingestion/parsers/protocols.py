"""Protocols and transport types for ingestion parsers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument


class RemoteDocumentPayload(BaseModel):
    """Fetched remote document bytes plus resolved transport metadata."""

    content: bytes
    final_url: str
    media_type: str | None = None
    filename: str | None = None
    size_bytes: int = Field(ge=0)
    inferred_format: DocumentFormat | None = None


@runtime_checkable
class DocumentParser(Protocol):
    """Typed contract implemented by all concrete document parsers."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def supported_formats(self) -> tuple[DocumentFormat, ...]: ...

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument: ...


@runtime_checkable
class RemoteDocumentFetcher(Protocol):
    """Fetch remote bytes for a source document."""

    def fetch(self, source: SourceDocument) -> RemoteDocumentPayload: ...


__all__ = [
    "DocumentParser",
    "RemoteDocumentFetcher",
    "RemoteDocumentPayload",
]