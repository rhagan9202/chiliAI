"""Tesseract-backed OCR adapter for scanned/image-only PDF pages.

Requires the optional ``[ocr]`` extra (``pdf2image`` + ``pytesseract``) plus a
system Tesseract and Poppler install. OCR is opt-in per deployment: nothing here
is imported unless an operator constructs and wires this adapter into a
``PdfParser``. The heavy dependencies are imported lazily via ``importlib`` so a
default install (without the extra) neither imports nor requires them.
"""

from __future__ import annotations

import importlib
from typing import Callable, cast

__all__ = ["TesseractOcrAdapter"]


class TesseractOcrAdapter:
    """Render a single PDF page to a raster image and OCR it with Tesseract."""

    def __init__(self, *, dpi: int = 200, language: str = "eng") -> None:
        self._dpi = dpi
        self._language = language

    def recognize_page(self, content: bytes, page_number: int) -> str:
        convert_from_bytes, image_to_string = _load_ocr_callables()
        images = cast(
            list[object],
            convert_from_bytes(
                content,
                dpi=self._dpi,
                first_page=page_number,
                last_page=page_number,
            ),
        )
        if not images:
            return ""
        return str(image_to_string(images[0], lang=self._language))


def _load_ocr_callables() -> tuple[Callable[..., object], Callable[..., object]]:
    """Import the optional OCR dependencies only when the adapter is used."""

    try:
        pdf2image_module = importlib.import_module("pdf2image")
        pytesseract_module = importlib.import_module("pytesseract")
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "The optional OCR dependencies are not installed. "
            "Install chili-backend[ocr] (pdf2image + pytesseract) and the system "
            "Tesseract + Poppler binaries."
        ) from exc

    convert_from_bytes = getattr(pdf2image_module, "convert_from_bytes", None)
    image_to_string = getattr(pytesseract_module, "image_to_string", None)
    if not callable(convert_from_bytes) or not callable(image_to_string):
        raise ImportError(
            "OCR dependencies are installed but the expected callables "
            "(pdf2image.convert_from_bytes / pytesseract.image_to_string) are missing."
        )
    return convert_from_bytes, image_to_string
