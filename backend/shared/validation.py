"""Reusable input validation helpers for API and ingestion (E10-S10).

These utilities enforce the limits declared in
:class:`config.schema.ValidationConfig`. They are deliberately stdlib-only
so they can be invoked from either the FastAPI gateway or the ingestion
module without dragging in extra dependencies.
"""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath, PureWindowsPath

__all__ = [
    "WINDOWS_RESERVED_NAMES",
    "sanitize_filename",
    "validate_content_type",
    "validate_query_length",
]


WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)


def _strip_path_traversal(name: str) -> str:
    """Drop any directory components, keeping only the leaf name."""

    posix_leaf = PurePosixPath(name).name
    if not posix_leaf:
        return ""
    windows_leaf = PureWindowsPath(posix_leaf).name
    return windows_leaf or ""


def sanitize_filename(name: str) -> str:
    """Return a safe filename with traversal sequences and control chars removed.

    Empty or inherently unsafe inputs collapse to ``"upload"`` so callers can
    always rely on a non-empty value.
    """

    if not isinstance(name, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        return "upload"

    normalized = unicodedata.normalize("NFC", name)
    leaf = _strip_path_traversal(normalized)
    cleaned = "".join(
        char
        for char in leaf
        if char not in {"\x00"} and not _is_disallowed_control(char)
    )
    cleaned = cleaned.replace("..", "").strip().strip(".")
    if not cleaned:
        return "upload"

    stem = cleaned.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    return cleaned


def _is_disallowed_control(char: str) -> bool:
    if char in {"\t", "\n", "\r"}:
        return True
    return unicodedata.category(char) == "Cc"


def validate_content_type(ct: str | None, allowed: set[str]) -> bool:
    """Return True when ``ct`` exactly matches one of ``allowed``."""

    if ct is None:
        return False
    primary = ct.split(";", 1)[0].strip().lower()
    return primary in {entry.lower() for entry in allowed}


def validate_query_length(s: str, max_len: int) -> str:
    """Strip and length-check a query string. Raises ``ValueError`` on overflow."""

    if not isinstance(s, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("Query must be a string.")
    trimmed = s.strip()
    if len(trimmed) > max_len:
        raise ValueError(
            f"Query length {len(trimmed)} exceeds maximum of {max_len} characters."
        )
    return trimmed
