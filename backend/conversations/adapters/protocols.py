"""Adapter-level protocol for conversation persistence backends."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from conversations.models import Conversation


@runtime_checkable
class ConversationRepository(Protocol):
    """Persist and query durable RAG chat conversations."""

    def create(self, conversation: Conversation) -> Conversation:
        """Insert a new conversation idempotently and return it."""
        ...

    def get(self, conversation_id: str) -> Conversation | None:
        """Return one conversation by id, or ``None`` if absent."""
        ...

    def save(
        self, conversation: Conversation, *, expected_updated_at: datetime
    ) -> Conversation:
        """Persist ``conversation`` (e.g. after appending messages), guarded.

        ``expected_updated_at`` is the ``updated_at`` the caller last read.
        The write is only applied if the stored row still has that
        ``updated_at`` -- otherwise another writer committed first and this
        raises ``conversations.exceptions.ConversationConcurrentModificationError``
        instead of silently overwriting that writer's message. Raises
        ``ConversationNotFoundError`` if the conversation no longer exists.
        """
        ...

    def list_by_kb(
        self, knowledge_base_id: str, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        """Return a page of a KB's conversations (most recently updated first).

        Without this the durable-conversation feature is invisible: RAG Chat
        can start a conversation but never resume one (UXA-403).
        """
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all conversations for a knowledge base; return rows removed."""
        ...


__all__ = ["ConversationRepository"]
