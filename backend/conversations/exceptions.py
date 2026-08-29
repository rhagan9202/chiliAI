"""Exception hierarchy for the conversations module."""

from __future__ import annotations

from shared.exceptions import ConcurrentModificationError


class ConversationError(Exception):
    """Base exception for conversation persistence failures."""


class ConversationPersistenceError(ConversationError):
    """Raised when a conversation cannot be persisted or read back."""


class ConversationNotFoundError(ConversationError):
    """Raised when a conversation is not found."""

    def __init__(self, conversation_id: str) -> None:
        super().__init__(f"Conversation '{conversation_id}' not found.")
        self.conversation_id = conversation_id


class ConversationConcurrentModificationError(
    ConversationError, ConcurrentModificationError
):
    """Raised when a conversation changed between the caller's read and its write.

    Follows the contract in ``backend/monitoring/README.md`` (monitoring.22):
    inherits from both this module's own error hierarchy (so module-internal
    and test code keeps catching it as a ``ConversationError``) and the
    cross-module ``shared.exceptions.ConcurrentModificationError`` marker (so
    a caller that only needs to know "was this a lost race" can catch that
    one type without importing every module's exception module).

    Distinct from ``ConversationPersistenceError``, which means the
    underlying store itself failed and may not be safe to retry. A lost race
    always is: reload and resubmit. ``ConversationService.append_messages``
    retries on this internally (appending is a pure merge, so a fresh read
    plus a re-applied append always converges); this type only escapes to a
    caller if that retry budget is exhausted.
    """

    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            f"Conversation '{conversation_id}' changed concurrently; reload it and retry."
        )
        self.conversation_id = conversation_id


__all__ = [
    "ConversationConcurrentModificationError",
    "ConversationError",
    "ConversationNotFoundError",
    "ConversationPersistenceError",
]
