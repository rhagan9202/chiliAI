"""Exception hierarchy for the explainability analytics module."""

from __future__ import annotations


class ExplainabilityError(Exception):
    """Base exception for explainability module failures."""


class ExplainabilityConfigurationError(ExplainabilityError):
    """Raised when an explainability request is invalid or incomplete."""


class ExplainabilityInsufficientEvidenceError(ExplainabilityError):
    """Raised when an alert cannot be explained with enough evidence."""


class ExplainabilitySourceError(ExplainabilityError):
    """Raised when the configured context source cannot return explainability data."""