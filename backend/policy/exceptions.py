"""Exception hierarchy for the policy module."""

from __future__ import annotations


class PolicyError(Exception):
    """Base exception for policy intelligence failures."""


class PolicyPersistenceError(PolicyError):
    """Raised when a policy item cannot be persisted or read back."""


class PolicyItemNotFoundError(PolicyError):
    """Raised when a policy item is not found within a knowledge base scope."""

    def __init__(self, knowledge_base_id: str, item_id: str) -> None:
        super().__init__(
            f"Policy item '{item_id}' not found in knowledge base '{knowledge_base_id}'."
        )
        self.knowledge_base_id = knowledge_base_id
        self.item_id = item_id


class PolicyItemAlreadyTriagedError(PolicyError):
    """Raised when triaging an item that already carries a disposition."""

    def __init__(self, knowledge_base_id: str, item_id: str) -> None:
        super().__init__(
            f"Policy item '{item_id}' in knowledge base '{knowledge_base_id}' "
            "has already been triaged."
        )
        self.knowledge_base_id = knowledge_base_id
        self.item_id = item_id


__all__ = [
    "PolicyError",
    "PolicyItemAlreadyTriagedError",
    "PolicyItemNotFoundError",
    "PolicyPersistenceError",
]
