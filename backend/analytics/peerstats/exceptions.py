"""Exceptions for the peerstats module."""

from __future__ import annotations


class PeerStatsError(Exception):
    """Base class for peerstats failures."""


class PeerStatsConfigurationError(PeerStatsError):
    """Raised when a peer metric spec is internally inconsistent at runtime."""


class PeerStatsSourceError(PeerStatsError):
    """Raised when loading record column aggregates fails."""


__all__ = [
    "PeerStatsConfigurationError",
    "PeerStatsError",
    "PeerStatsSourceError",
]
