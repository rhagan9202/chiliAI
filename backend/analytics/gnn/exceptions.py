"""Exception hierarchy for the gnn analytics module."""

from __future__ import annotations


class GnnError(Exception):
    """Base exception for gnn module failures."""


class GnnConfigurationError(GnnError):
    """Raised when a gnn request is invalid or incomplete."""


class GnnInsufficientGraphError(GnnError):
    """Raised when a graph snapshot is too small for analysis."""


class GnnSourceError(GnnError):
    """Raised when the configured snapshot source cannot return graph data."""