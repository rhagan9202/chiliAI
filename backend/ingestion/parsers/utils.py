"""Shared utilities for the parser subsystem."""

from __future__ import annotations

from pathlib import PurePosixPath

from ingestion.models import DocumentFormat
from ingestion.parsers.exceptions import ContentDecodingError

_CONTENT_TYPE_MAP: dict[str, DocumentFormat] = {
    "application/json": DocumentFormat.JSON,
    "application/pdf": DocumentFormat.PDF,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentFormat.XLSX,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentFormat.DOCX,
    "text/csv": DocumentFormat.CSV,
    "text/plain": DocumentFormat.TXT,
}

_EXTENSION_MAP: dict[str, DocumentFormat] = {
    ".csv": DocumentFormat.CSV,
    ".docx": DocumentFormat.DOCX,
    ".html": DocumentFormat.HTML,
    ".htm": DocumentFormat.HTML,
    ".json": DocumentFormat.JSON,
    ".pdf": DocumentFormat.PDF,
    ".txt": DocumentFormat.TXT,
    ".xlsx": DocumentFormat.XLSX,
}


def normalize_newlines(text: str) -> str:
    """Normalize text content to LF newlines."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_text_content(content: bytes) -> tuple[str, str]:
    """Decode text content using a small fallback chain."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return normalize_newlines(content.decode(encoding)), encoding
        except UnicodeDecodeError:
            continue
    raise ContentDecodingError("Unable to decode text content with supported encodings.")


def infer_format_from_content_type(content_type: str | None) -> DocumentFormat | None:
    """Infer document format from an HTTP content type value."""
    if content_type is None:
        return None
    media_type = content_type.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_MAP.get(media_type)


def infer_format_from_filename(filename: str | None) -> DocumentFormat | None:
    """Infer document format from a filename or URL path."""
    if not filename:
        return None
    suffix = PurePosixPath(filename).suffix.lower()
    return _EXTENSION_MAP.get(suffix)


def build_parser_metadata(**kwargs: object) -> dict[str, object]:
    """Create metadata dict excluding null values."""
    return {key: value for key, value in kwargs.items() if value is not None}