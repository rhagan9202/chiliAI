"""Exception hierarchy for the analytics metrics package."""

from __future__ import annotations


class MetricsError(Exception):
    """Base exception for analytics metrics failures."""


class MetricsRepositoryError(MetricsError):
    """Raised when the entity-metric repository cannot read or write metrics."""


__all__ = [
    "MetricsError",
    "MetricsRepositoryError",
]
