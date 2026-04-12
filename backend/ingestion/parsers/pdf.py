"""PDF parser."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.utils import build_parser_metadata, normalize_newlines


class PdfParser:
    """Extract text from text-based PDF documents."""

    name = "pdf"
    version = "1.0"
    supported_formats = (DocumentFormat.PDF,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as exc:
            raise ParserError(f"Unable to read PDF content: {exc}") from exc

        if reader.is_encrypted:
            raise ParserError("Encrypted PDF files are not supported.")

        page_texts = [normalize_newlines(page.extract_text() or "") for page in reader.pages]
        text = "\n\n".join(part.strip() for part in page_texts if part.strip())
        if not text:
            raise ParserError("PDF does not contain extractable text.")

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=text,
            parser_name=self.name,
            parser_version=self.version,
            parser_metadata=build_parser_metadata(
                page_count=len(reader.pages),
                non_empty_pages=sum(1 for part in page_texts if part.strip()),
            ),
        )