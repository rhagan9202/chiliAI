"""In-memory conversation repository for tests and local development."""

from __future__ import annotations

import threading
from datetime import datetime

from conversations.exceptions import (
    ConversationConcurrentModificationError,
    ConversationNotFoundError,
)
from conversations.models import Conversation

__all__ = ["InMemoryConversationRepository"]


class InMemoryConversationRepository:
    """A dict-backed ``ConversationRepository`` keyed by conversation id."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        # Postgres gets true CAS atomicity for free from row-level locking:
        # a concurrent `UPDATE ... WHERE updated_at = %s` against the same
        # row serializes, so the second is evaluated against the
        # already-committed value. `save` below is read-compare-write across
        # separate Python steps with no such guarantee, so it needs its own
        # lock to give both adapters identical semantics (mirrors
        # `InMemoryCaseRepository.update`).
        self._save_lock = threading.Lock()

    def create(self, conversation: Conversation) -> Conversation:
        self._conversations.setdefault(conversation.id, conversation)
        return self._conversations[conversation.id]

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def save(
        self, conversation: Conversation, *, expected_updated_at: datetime
    ) -> Conversation:
        # The compare and the write must be atomic, or two threads can both
        # pass the compare against the same stale value and both write --
        # the second write silently discarding the first.
        with self._save_lock:
            existing = self._conversations.get(conversation.id)
            if existing is None:
                raise ConversationNotFoundError(conversation.id)
            if existing.updated_at != expected_updated_at:
                raise ConversationConcurrentModificationError(conversation.id)
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
