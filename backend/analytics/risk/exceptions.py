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