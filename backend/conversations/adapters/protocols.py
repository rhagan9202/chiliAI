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
