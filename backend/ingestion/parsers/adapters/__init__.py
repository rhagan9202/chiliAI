"""Concrete optional adapters for the parser subsystem (e.g. OCR)."""

from __future__ import annotations

from ingestion.parsers.adapters.tesseract import TesseractOcrAdapter

__all__ = ["TesseractOcrAdapter"]
