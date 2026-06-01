"""Exception hierarchy for the cases module."""

from __future__ import annotations


class CaseError(Exception):
    """Base exception for case management failures."""


class CasePersistenceError(CaseError):
    """Raised when a case cannot be persisted or read back."""


class CaseNotFoundError(CaseError):
    """Raised when a case is not found within a knowledge base scope."""

    def __init__(self, knowledge_base_id: str, case_id: str) -> None:
        super().__init__(
            f"Case '{case_id}' not found in knowledge base '{knowledge_base_id}'."
        )
        self.knowledge_base_id = knowledge_base_id
        self.case_id = case_id


__all__ = [
    "CaseError",
    "CaseNotFoundError",
    "CasePersistenceError",
]
