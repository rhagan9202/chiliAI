"""Conversations are listable per knowledge base (UXA-403).

The backend persisted conversations and the dev seed created one, but nothing
could enumerate them — the repository had create/get/save/delete_by_kb and no
list. So RAG Chat had a "New conversation" button and no way to resume an
existing one; the durable-conversation feature was invisible.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.models import Conversation, ConversationMessage
from conversations.service import create_conversation_service

BASE = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _conversation(
    conversation_id: str,
    *,
    knowledge_base_id: str = "kb-1",
    minutes: int = 0,
    messages: list[ConversationMessage] | None = None,
) -> Conversation:
    return Conversation(
        id=conversation_id,
        knowledge_base_id=knowledge_base_id,
        title=f"Conversation {conversation_id}",
        messages=messages or [],
        created_at=BASE,
        updated_at=BASE + timedelta(minutes=minutes),
    )


def _repository() -> InMemoryConversationRepository:
    repository = InMemoryConversationRepository()
    repository.create(_conversation("c-1", minutes=1))
    repository.create(_conversation("c-2", minutes=3))
    repository.create(_conversation("c-3", knowledge_base_id="kb-2", minutes=5))
    return repository


def test_lists_only_the_named_knowledge_bases_conversations() -> None:
    conversations, total = _repository().list_by_kb("kb-1", limit=10, offset=0)

    assert total == 2
    assert {conversation.id for conversation in conversations} == {"c-1", "c-2"}


def test_orders_most_recently_updated_first() -> None:
    # A conversation list is for resuming; the one you were just in leads.
    conversations, _ = _repository().list_by_kb("kb-1", limit=10, offset=0)

    assert [conversation.id for conversation in conversations] == ["c-2", "c-1"]


def test_paginates_within_the_scoped_set() -> None:
    conversations, total = _repository().list_by_kb("kb-1", limit=1, offset=1)

    assert total == 2
    assert [conversation.id for conversation in conversations] == ["c-1"]


def test_returns_nothing_for_a_knowledge_base_with_no_conversations() -> None:
    assert _repository().list_by_kb("kb-ghost", limit=10, offset=0) == ([], 0)


def test_service_exposes_the_listing() -> None:
    service = create_conversation_service(_repository())

    conversations, total = service.list(knowledge_base_id="kb-1", limit=10, offset=0)

    assert total == 2
    assert [conversation.id for conversation in conversations] == ["c-2", "c-1"]
