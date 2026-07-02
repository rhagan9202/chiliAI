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


@runtime_checkable
class OcrAdapterProtocol(Protocol):
    """Recognize text from a single PDF page that yielded no extractable text.

    Implementations receive the full document ``content`` plus the 1-based
    ``page_number`` to render and OCR, returning the recognized text (empty
    string when nothing is found). Kept dependency-light so the heavy OCR
    libraries live only in concrete adapters behind the optional ``[ocr]`` extra.
    """

    def recognize_page(self, content: bytes, page_number: int) -> str: ...


__all__ = [
    "DocumentParser",
    "OcrAdapterProtocol",
    "RemoteDocumentFetcher",
    "RemoteDocumentPayload",
]