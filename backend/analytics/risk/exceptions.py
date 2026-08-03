"""Exception hierarchy for the risk analytics module."""

from __future__ import annotations


class RiskError(Exception):
    """Base exception for risk module failures."""


class RiskConfigurationError(RiskError):
    """Raised when a risk request is invalid or incomplete."""


class RiskInsufficientSignalsError(RiskError):
    """Raised when a risk profile does not contain enough signal coverage."""


class RiskSourceError(RiskError):
    """Raised when the configured signal source cannot return risk data."""


class RiskHistoryError(RiskError):
    """Raised when the risk-history store cannot read or write assessments."""


class RiskProjectionError(RiskError):
    """Raised when the risk projection read model cannot be persisted or loaded."""


__all__ = [
    "RiskConfigurationError",
    "RiskError",
    "RiskHistoryError",
    "RiskInsufficientSignalsError",
    "RiskProjectionError",
    "RiskSourceError",
]
