"""PDF parser."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from ingestion.models import DocumentFormat, ParsedDocument, ParserWarning, SourceDocument
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.protocols import OcrAdapterProtocol
from ingestion.parsers.utils import build_parser_metadata, normalize_newlines

__all__ = ["PdfParser"]


class PdfParser:
    """Extract text from text-based PDF documents, with optional OCR fallback.

    When an ``ocr_adapter`` is supplied, pages that yield no extractable text are
    OCR'd individually (scanned/image-only pages). Without an adapter the behavior
    is unchanged — a text-less PDF raises ``ParserError`` — so OCR is opt-in.
    """

    name = "pdf"
    version = "2.0"
    supported_formats = (DocumentFormat.PDF,)

    def __init__(self, ocr_adapter: OcrAdapterProtocol | None = None) -> None:
        self._ocr_adapter = ocr_adapter

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as exc:
            raise ParserError(f"Unable to read PDF content: {exc}") from exc

        if reader.is_encrypted:
            raise ParserError("Encrypted PDF files are not supported.")

        page_texts = [normalize_newlines(page.extract_text() or "") for page in reader.pages]

        ocr_used = False
        if self._ocr_adapter is not None:
            for index, part in enumerate(page_texts):
                if part.strip():
                    continue
                recognized = normalize_newlines(self._ocr_adapter.recognize_page(content, index + 1))
                if recognized.strip():
                    page_texts[index] = recognized
                    ocr_used = True

        text = "\n\n".join(part.strip() for part in page_texts if part.strip())
        if not text:
            raise ParserError("PDF does not contain extractable text.")

        warnings = [
            ParserWarning(
                code="pdf.empty_page",
                message=f"Page {page_number} contained no extractable text.",
                severity="warning",
                page_number=page_number,
            )
            for page_number, part in enumerate(page_texts, start=1)
            if not part.strip()
        ]

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=text,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parser_metadata=build_parser_metadata(
                page_count=len(reader.pages),
                non_empty_pages=sum(1 for part in page_texts if part.strip()),
                ocr_used=ocr_used,
            ),
        )
