"""Exception hierarchy for the rag module."""

from __future__ import annotations


class RagError(Exception):
    """Base exception for rag module failures."""


class RagConfigurationError(RagError):
    """Raised when a rag request is invalid or incomplete."""


class RagRetrievalError(RagError):
    """Raised when retrieval or graph expansion fails."""


class RagGenerationError(RagError):
    """Raised when answer generation fails."""