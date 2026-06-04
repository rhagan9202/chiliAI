"""Exception hierarchy for the conversations module."""

from __future__ import annotations


class ConversationError(Exception):
    """Base exception for conversation persistence failures."""


class ConversationPersistenceError(ConversationError):
    """Raised when a conversation cannot be persisted or read back."""


class ConversationNotFoundError(ConversationError):
    """Raised when a conversation is not found."""

    def __init__(self, conversation_id: str) -> None:
        super().__init__(f"Conversation '{conversation_id}' not found.")
        self.conversation_id = conversation_id


__all__ = [
    "ConversationError",
    "ConversationNotFoundError",
    "ConversationPersistenceError",
]
