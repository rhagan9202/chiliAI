"""Exception hierarchy for the graph module."""

from __future__ import annotations


class GraphError(Exception):
    """Base exception for graph module failures."""


class GraphPersistenceError(GraphError):
    """Raised when graph state or graph artifacts cannot be persisted."""