"""Exception hierarchy for the gnn analytics module."""

from __future__ import annotations


class GnnError(Exception):
    """Base exception for gnn module failures."""


class GnnConfigurationError(GnnError):
    """Raised when a gnn request is invalid or incomplete."""


class GnnDisabledError(GnnError):
    """Raised when GNN analysis is disabled by domain configuration."""


class GnnInsufficientGraphError(GnnError):
    """Raised when a graph snapshot is too small for analysis."""


class GnnSnapshotUnavailableError(GnnError):
    """Raised when no graph snapshot exists yet for a knowledge base."""


class GnnSourceError(GnnError):
    """Raised when the configured snapshot source cannot return graph data."""


__all__ = [
    "GnnConfigurationError",
    "GnnDisabledError",
    "GnnError",
    "GnnInsufficientGraphError",
    "GnnSnapshotUnavailableError",
    "GnnSourceError",
]