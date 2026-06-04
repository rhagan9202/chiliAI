"""Integration tests for the Postgres conversation repository (BL-012).

Written-not-run: requires DATABASE_URL + the 0005_conversations migration.
"""

from __future__ import annotations

import pytest

from conversations.adapters.postgres import PostgresConversationRepository
from conversations.models import (
    Conversation,
    ConversationCitation,
    ConversationMessage,
)

pytestmark = pytest.mark.integration


def _conversation(conversation_id: str = "conv-pg") -> Conversation:
    return Conversation(
        id=conversation_id,
        title="Provider anomaly review",
        knowledge_base_id="kb-pg",
    )


def test_create_then_get_round_trips(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    repo = conversation_pg_repo
    repo.create(_conversation())

    stored = repo.get("conv-pg")
    assert stored is not None
    assert stored.knowledge_base_id == "kb-pg"
    assert stored.messages == []


def test_save_round_trips_messages_with_citations(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    repo = conversation_pg_repo
    created = repo.create(_conversation())

    message = ConversationMessage(
        id="m-1",
        role="assistant",
        content="High risk.",
        citation_ids=["content-1"],
        citations=[
            ConversationCitation(
                record_id="record-1",
                content_id="content-1",
                score=0.9,
                snippet="peer deviation",
                chunk_index=2,
            )
        ],
    )
    repo.save(created.model_copy(update={"messages": [message]}))

    stored = repo.get("conv-pg")
    assert stored is not None
    assert stored.messages[0].citations[0].content_id == "content-1"
    assert stored.messages[0].citations[0].chunk_index == 2


def test_create_is_idempotent(
    conversation_pg_repo: PostgresConversationRepository,
) -> None:
    repo = conversation_pg_repo
    repo.create(_conversation())
    repo.create(_conversation().model_copy(update={"title": "Other"}))

    stored = repo.get("conv-pg")
    assert stored is not None
    assert stored.title == "Provider anomaly review"
