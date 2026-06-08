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


def test_delete_by_kb_removes_rows_and_returns_count(
    database_url: str,
) -> None:
    from config.schema import DatabaseConfig
    from database.runtime import create_connection_provider

    unique_kb = "kb-delete-test-unique-001"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresConversationRepository(provider)
    try:
        conv_a = Conversation(
            id="conv-del-a",
            title="Delete test A",
            knowledge_base_id=unique_kb,
        )
        conv_b = Conversation(
            id="conv-del-b",
            title="Delete test B",
            knowledge_base_id=unique_kb,
        )
        conv_other = Conversation(
            id="conv-del-other",
            title="Other KB",
            knowledge_base_id="kb-other-unique-001",
        )
        repo.create(conv_a)
        repo.create(conv_b)
        repo.create(conv_other)

        count = repo.delete_by_kb(unique_kb)

        assert count == 2
        assert repo.get("conv-del-a") is None
        assert repo.get("conv-del-b") is None
        # row from a different KB must survive
        assert repo.get("conv-del-other") is not None

        # idempotent: second call returns 0
        second = repo.delete_by_kb(unique_kb)
        assert second == 0
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE conversation_id IN (%s, %s, %s)",
                ("conv-del-a", "conv-del-b", "conv-del-other"),
            )
            conn.commit()
        provider.close()
