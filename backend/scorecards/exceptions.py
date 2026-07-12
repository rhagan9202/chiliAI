"""Scorecard evaluation exceptions."""

from __future__ import annotations


class ScorecardEvaluationError(Exception):
    """Base class for deterministic scorecard evaluation failures."""


class ScorecardFormulaError(ScorecardEvaluationError):
    """Raised when one configured metric formula cannot be evaluated."""


class ScorecardPersistenceError(ScorecardEvaluationError):
    """Raised when durable scorecard run persistence fails."""


class ScorecardRunNotFoundError(ScorecardEvaluationError):
    """Raised when a durable scorecard run is missing."""

    def __init__(self, knowledge_base_id: str, run_id: str) -> None:
        super().__init__(
            f"Scorecard run '{run_id}' was not found for knowledge base "
            f"'{knowledge_base_id}'."
        )


class ScorecardTemplateNotFoundError(ScorecardEvaluationError):
    """Raised when a configured scorecard template is missing."""

    def __init__(self, template_id: str) -> None:
        super().__init__(f"Scorecard template '{template_id}' was not found.")


class ScorecardExportNotFoundError(ScorecardEvaluationError):
    """Raised when a stored scorecard run does not have the requested export."""

    def __init__(self, run_id: str, export_format: str) -> None:
        super().__init__(
            f"Scorecard run '{run_id}' does not have a '{export_format}' export."
        )


__all__ = [
    "ScorecardExportNotFoundError",
    "ScorecardEvaluationError",
    "ScorecardFormulaError",
    "ScorecardPersistenceError",
    "ScorecardRunNotFoundError",
    "ScorecardTemplateNotFoundError",
]
