"""Plain-text parser."""

from __future__ import annotations

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument
from ingestion.parsers.utils import build_parser_metadata, decode_text_content

__all__ = ["TextParser"]


class TextParser:
    """Parse plain-text bytes into a normalized ParsedDocument."""

    name = "text"
    version = "1.0"
    supported_formats = (DocumentFormat.TXT,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        text, encoding = decode_text_content(content)
        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=text,
            parser_name=self.name,
            parser_version=self.version,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                content_length=len(content),
            ),
        )