"""Conversation orchestration over a durable repository."""

from __future__ import annotations

from conversations.adapters.protocols import ConversationRepository
from conversations.exceptions import (
    ConversationConcurrentModificationError,
    ConversationNotFoundError,
)
from conversations.models import Conversation, ConversationMessage
from shared.utils import generate_id, utc_now

__all__ = ["ConversationService", "create_conversation_service"]

_DEFAULT_TITLE = "Untitled investigation chat"

# Appending is a pure merge (list concatenation): unlike a status transition,
# there is no legitimate reason two concurrent appends can't both land, so a
# lost CAS race here is always safe to resolve by re-reading and retrying --
# no caller-visible 409 needed on the common path. Bounded rather than
# unbounded so a pathologically hot conversation fails loudly (as
# ConversationConcurrentModificationError, still a "reload and retry" signal
# per the contract) instead of spinning forever.
_MAX_APPEND_ATTEMPTS = 10


class ConversationService:
    """Create, read, and append messages to durable chat conversations."""

    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        knowledge_base_id: str,
        title: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            id=generate_id(),
            title=title or _DEFAULT_TITLE,
            knowledge_base_id=knowledge_base_id,
        )
        return self._repository.create(conversation)

    def list(
        self, *, knowledge_base_id: str, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        """Return a KB's conversations, most recently updated first."""
        return self._repository.list_by_kb(
            knowledge_base_id, limit=limit, offset=offset
        )

    def get(self, conversation_id: str) -> Conversation | None:
        return self._repository.get(conversation_id)

    def append_messages(
        self,
        conversation_id: str,
        messages: list[ConversationMessage],
    ) -> Conversation:
        """Append messages, guarding the read-modify-write against a concurrent turn.

        Two turns landing at once both read the same message list; without a
        guard, the second ``save`` silently discards the first (BL-012-06).
        ``save`` now compare-and-sets on ``updated_at`` and raises
        ``ConversationConcurrentModificationError`` on a lost race. Because
        appending is a pure merge -- both turns belong in the final list
        regardless of order -- this retries on that error rather than
        surfacing it: re-read, re-apply the append on top of the fresh
        state, and try again.
        """
        last_error: ConversationConcurrentModificationError | None = None
        for _ in range(_MAX_APPEND_ATTEMPTS):
            existing = self._repository.get(conversation_id)
            if existing is None:
                raise ConversationNotFoundError(conversation_id)
            updated = existing.model_copy(
                update={
                    "messages": [*existing.messages, *messages],
                    # Owned here rather than in an adapter: the in-memory adapter
                    # used to re-stamp this inside save() and the Postgres one did
                    # not, so "most recently updated first" was really creation
                    # order -- in production only.
                    "updated_at": utc_now(),
                }
            )
            try:
                return self._repository.save(
                    updated, expected_updated_at=existing.updated_at
                )
            except ConversationConcurrentModificationError as exc:
                last_error = exc
                continue
        assert last_error is not None  # loop only exits via return or continue
        raise last_error


def create_conversation_service(
    repository: ConversationRepository,
) -> ConversationService:
    """Create the default conversation service."""
    return ConversationService(repository)
