"""Parser registry and format dispatch."""

from __future__ import annotations

from collections.abc import Iterable

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument
from ingestion.parsers.exceptions import UnsupportedFormatError
from ingestion.parsers.protocols import DocumentParser

__all__ = ["ParserRegistry", "create_default_registry"]


class ParserRegistry:
    """Map document formats to parser implementations."""

    def __init__(self, parsers: Iterable[DocumentParser] | None = None) -> None:
        self._parsers: dict[DocumentFormat, DocumentParser] = {}
        if parsers is not None:
            for parser in parsers:
                self.register(parser)

    def register(self, parser: DocumentParser) -> None:
        for document_format in parser.supported_formats:
            self._parsers[document_format] = parser

    def get_parser(self, document_format: DocumentFormat) -> DocumentParser:
        parser = self._parsers.get(document_format)
        if parser is None:
            raise UnsupportedFormatError(f"No parser registered for format '{document_format.value}'.")
        return parser

    def supports(self, document_format: DocumentFormat) -> bool:
        """Return whether a parser is registered for the given format."""
        return document_format in self._parsers

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        if source.document_format is None:
            raise UnsupportedFormatError("Source document format is not resolved.")
        return self.get_parser(source.document_format).parse(source, content)


def create_default_registry() -> ParserRegistry:
    """Return a parser registry populated with built-in parsers."""
    from ingestion.parsers.csv import CsvParser
    from ingestion.parsers.docx import DocxParser
    from ingestion.parsers.html import HtmlParser
    from ingestion.parsers.json import JsonParser
    from ingestion.parsers.pdf import PdfParser
    from ingestion.parsers.txt import TextParser
    from ingestion.parsers.xlsx import XlsxParser

    return ParserRegistry(
        parsers=[
            CsvParser(),
            DocxParser(),
            HtmlParser(),
            JsonParser(),
            PdfParser(),
            TextParser(),
            XlsxParser(),
        ]
    )
