"""In-memory conversation repository for tests and local development."""

from __future__ import annotations

from conversations.models import Conversation

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
        self._conversations[conversation.id] = conversation
        return conversation

    def list_by_kb(
        self, knowledge_base_id: str, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        scoped = [
            conversation
            for conversation in self._conversations.values()
            if conversation.knowledge_base_id == knowledge_base_id
        ]
        # Most recently updated first: a list exists to resume from, and the
        # conversation you were just in should lead it.
        scoped.sort(key=lambda conversation: conversation.updated_at, reverse=True)
        return scoped[offset : offset + limit], len(scoped)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        to_delete = [
            cid
            for cid, c in self._conversations.items()
            if c.knowledge_base_id == knowledge_base_id
        ]
        for cid in to_delete:
            del self._conversations[cid]
        return len(to_delete)
