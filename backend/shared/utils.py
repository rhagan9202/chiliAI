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


# TODO(production): Add utility functions required by multiple modules:
# - utc_now() -> datetime: canonical UTC timestamp (deduplicate from events/types.py)
# - json_serialize(obj) -> str: Pydantic-aware JSON serializer with datetime handling
# - retry(max_attempts, backoff_factor, retryable_exceptions): decorator for transient
#   failure retry with exponential backoff — needed by all service modules
# - truncate_text(text, max_chars) -> str: safe truncation preserving word boundaries


__all__ = [
    "generate_id",
    "normalize_text",
]
