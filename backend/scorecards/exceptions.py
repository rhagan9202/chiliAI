"""Scorecard evaluation exceptions."""

from __future__ import annotations


class ScorecardEvaluationError(Exception):
    """Base class for deterministic scorecard evaluation failures."""


class ScorecardFormulaError(ScorecardEvaluationError):
    """Raised when one configured metric formula cannot be evaluated."""


__all__ = [
    "ScorecardEvaluationError",
    "ScorecardFormulaError",
]
