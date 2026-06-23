"""Plain-text parser."""

from __future__ import annotations

from ingestion.models import DocumentFormat, ParsedDocument, ParserWarning, SourceDocument
from ingestion.parsers.utils import build_parser_metadata, charset_fallback_warning, decode_text_content

__all__ = ["TextParser"]


class TextParser:
    """Parse plain-text bytes into a normalized ParsedDocument."""

    name = "text"
    version = "1.0"
    supported_formats = (DocumentFormat.TXT,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        text, encoding = decode_text_content(content)
        warnings: list[ParserWarning] = []
        charset = charset_fallback_warning("text", encoding)
        if charset is not None:
            warnings.append(charset)
        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=text,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                content_length=len(content),
            ),
        )