"""Exception hierarchy for the vectorstore module."""

from __future__ import annotations


class VectorError(Exception):
    """Base exception for vectorstore module failures."""


class VectorDimensionMismatchError(VectorError):
    """Raised when vector dimensions do not match a namespace dimension."""


class VectorStoreError(VectorError):
    """Raised when vector storage or search operations fail."""