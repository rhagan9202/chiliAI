"""Integration test for the Tesseract OCR PDF fallback (ingestion.03).

Skipped unless the optional ``[ocr]`` extra (pdf2image + pytesseract + Pillow)
and the system Tesseract/Poppler binaries are installed. Runs the real
``TesseractOcrAdapter`` against an image-only PDF rendered from text.
"""

from __future__ import annotations

from io import BytesIO

import pytest

pytest.importorskip("pdf2image")
pytest.importorskip("pytesseract")
PIL_image = pytest.importorskip("PIL.Image")
PIL_draw = pytest.importorskip("PIL.ImageDraw")

from ingestion.models import DocumentFormat, SourceDocument, SourceType  # noqa: E402
from ingestion.parsers.adapters.tesseract import TesseractOcrAdapter  # noqa: E402
from ingestion.parsers.pdf import PdfParser  # noqa: E402

pytestmark = pytest.mark.integration


def _image_only_pdf(text: str) -> bytes:
    """Render text onto a blank image and save it as a single-page image PDF."""
    image = PIL_image.new("RGB", (1000, 300), color="white")
    draw = PIL_draw.Draw(image)
    draw.text((40, 120), text, fill="black")
    # Upscale so the default font is large enough for reliable recognition.
    image = image.resize((2000, 600))
    buffer = BytesIO()
    image.save(buffer, format="PDF")
    return buffer.getvalue()


def _source() -> SourceDocument:
    return SourceDocument(
        id="doc-ocr",
        source_type=SourceType.FILE_UPLOAD,
        document_format=DocumentFormat.PDF,
        filename="scan.pdf",
    )


def test_tesseract_adapter_recognizes_image_pdf_through_parser() -> None:
    pdf_bytes = _image_only_pdf("INVOICE 12345")

    parser = PdfParser(ocr_adapter=TesseractOcrAdapter())
    parsed = parser.parse(_source(), pdf_bytes)

    assert parsed.parser_metadata["ocr_used"] is True
    assert "INVOICE" in (parsed.text_content or "").upper()
