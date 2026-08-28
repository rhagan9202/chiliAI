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


class AlertAlreadyAttachedError(CaseError):
    """Raised when an alert is attached to a case that already holds it."""

    def __init__(self, case_id: str, alert_id: str) -> None:
        super().__init__(f"Alert '{alert_id}' is already attached to case '{case_id}'.")
        self.case_id = case_id
        self.alert_id = alert_id


class CaseConcurrentModificationError(CaseError):
    """Raised when a case changed between the caller's read and its write."""

    def __init__(self, knowledge_base_id: str, case_id: str) -> None:
        super().__init__(
            f"Case '{case_id}' in knowledge base '{knowledge_base_id}' was modified "
            "concurrently; reload it and retry."
        )
        self.knowledge_base_id = knowledge_base_id
        self.case_id = case_id


__all__ = [
    "AlertAlreadyAttachedError",
    "CaseConcurrentModificationError",
    "CaseError",
    "CaseNotFoundError",
    "CasePersistenceError",
]
