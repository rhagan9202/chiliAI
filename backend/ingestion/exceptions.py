"""Ingestion module exceptions."""

from __future__ import annotations

__all__ = ["DocumentStatusPersistenceError"]


class DocumentStatusPersistenceError(RuntimeError):
    """Raised when the document status store cannot read or write a row."""
