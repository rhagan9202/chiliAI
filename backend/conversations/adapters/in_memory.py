"""In-memory conversation repository for tests and local development."""

from __future__ import annotations

from conversations.models import Conversation
from shared.utils import utc_now

__all__ = ["InMemoryConversationRepository"]


class InMemoryConversationRepository:
    """A dict-backed ``ConversationRepository`` keyed by conversation id."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(self, conversation: Conversation) -> Conversation:
        self._conversations.setdefault(conversation.id, conversation)
        return self._conversations[conversation.id]

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def save(self, conversation: Conversation) -> Conversation:
        updated = conversation.model_copy(update={"updated_at": utc_now()})
        self._conversations[updated.id] = updated
        return updated
