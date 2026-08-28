"""Conversation orchestration over a durable repository."""

from __future__ import annotations

from conversations.adapters.protocols import ConversationRepository
from conversations.exceptions import ConversationNotFoundError
from conversations.models import Conversation, ConversationMessage
from shared.utils import generate_id, utc_now

__all__ = ["ConversationService", "create_conversation_service"]

_DEFAULT_TITLE = "Untitled investigation chat"


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
        return self._repository.save(updated)


def create_conversation_service(
    repository: ConversationRepository,
) -> ConversationService:
    """Create the default conversation service."""
    return ConversationService(repository)
