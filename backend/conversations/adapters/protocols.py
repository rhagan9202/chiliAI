"""Adapter-level protocol for conversation persistence backends."""

from __future__ import annotations

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

    def save(self, conversation: Conversation) -> Conversation:
        """Upsert a conversation (e.g. after appending messages) and return it."""
        ...


__all__ = ["ConversationRepository"]
