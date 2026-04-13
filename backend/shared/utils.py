"""Small general-purpose utilities for the shared library."""

from __future__ import annotations

import re
import uuid


def generate_id() -> str:
    """Return a new UUID4 string."""
    return str(uuid.uuid4())


def normalize_text(text: str) -> str:
    """Lowercase, strip, and collapse internal whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


__all__ = [
    "generate_id",
    "normalize_text",
]
