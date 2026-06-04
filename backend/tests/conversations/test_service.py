"""Tests for the conversation service over a durable repository (BL-012)."""

from __future__ import annotations

import pytest

from conversations.adapters.in_memory import InMemoryConversationRepository
from conversations.exceptions import ConversationNotFoundError
from conversations.models import ConversationMessage
from conversations.service import create_conversation_service


def test_create_defaults_title_when_absent() -> None:
    service = create_conversation_service(InMemoryConversationRepository())

    conversation = service.create(knowledge_base_id="kb-1")

    assert conversation.title == "Untitled investigation chat"
    assert conversation.knowledge_base_id == "kb-1"
    assert conversation.id


def test_create_uses_supplied_title() -> None:
    service = create_conversation_service(InMemoryConversationRepository())

    conversation = service.create(knowledge_base_id="kb-1", title="Triage")

    assert conversation.title == "Triage"


def test_append_messages_persists_in_order() -> None:
    service = create_conversation_service(InMemoryConversationRepository())
    conversation = service.create(knowledge_base_id="kb-1")

    user = ConversationMessage(id="u-1", role="user", content="Why risky?")
    assistant = ConversationMessage(id="a-1", role="assistant", content="Because.")
    updated = service.append_messages(conversation.id, [user, assistant])

    assert [m.id for m in updated.messages] == ["u-1", "a-1"]
    reread = service.get(conversation.id)
    assert reread is not None
    assert len(reread.messages) == 2


def test_append_messages_unknown_conversation_raises() -> None:
    service = create_conversation_service(InMemoryConversationRepository())

    with pytest.raises(ConversationNotFoundError):
        service.append_messages("missing", [])
