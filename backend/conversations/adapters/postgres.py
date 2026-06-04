"""Postgres-backed conversation repository.

Depends only on the psycopg-free ``database.ConnectionProvider`` protocol. The
``messages`` column is jsonb, written with an explicit ``::jsonb`` cast over a
serialized-JSON text parameter (mirrors ``cases.adapters.postgres``).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from conversations.exceptions import ConversationPersistenceError
from conversations.models import Conversation, ConversationMessage
from database.protocols import ConnectionProvider, Row

_COLUMNS = (
    "conversation_id, title, knowledge_base_id, messages, created_at, updated_at"
)

_INSERT_SQL = f"""
    INSERT INTO conversations ({_COLUMNS})
    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
    ON CONFLICT (conversation_id) DO NOTHING
"""

_GET_SQL = f"""
    SELECT {_COLUMNS}
    FROM conversations
    WHERE conversation_id = %s
"""

_UPSERT_SQL = f"""
    INSERT INTO conversations ({_COLUMNS})
    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
    ON CONFLICT (conversation_id) DO UPDATE
    SET title = EXCLUDED.title,
        knowledge_base_id = EXCLUDED.knowledge_base_id,
        messages = EXCLUDED.messages,
        updated_at = EXCLUDED.updated_at
"""


class PostgresConversationRepository:
    """A ``ConversationRepository`` backed by the ``conversations`` table."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def create(self, conversation: Conversation) -> Conversation:
        try:
            with self._provider.connection() as conn:
                conn.execute(_INSERT_SQL, self._row_params(conversation))
                conn.commit()
        except Exception as exc:
            raise ConversationPersistenceError("Failed to persist conversation.") from exc
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        try:
            with self._provider.connection() as conn:
                row = conn.execute(_GET_SQL, (conversation_id,)).fetchone()
        except Exception as exc:
            raise ConversationPersistenceError("Failed to load conversation.") from exc
        return None if row is None else _row_to_conversation(row)

    def save(self, conversation: Conversation) -> Conversation:
        try:
            with self._provider.connection() as conn:
                conn.execute(_UPSERT_SQL, self._row_params(conversation))
                conn.commit()
        except Exception as exc:
            raise ConversationPersistenceError("Failed to save conversation.") from exc
        return conversation

    @staticmethod
    def _row_params(conversation: Conversation) -> tuple[object, ...]:
        return (
            conversation.id,
            conversation.title,
            conversation.knowledge_base_id,
            _messages_to_json(conversation.messages),
            conversation.created_at,
            conversation.updated_at,
        )


def _messages_to_json(messages: list[ConversationMessage]) -> str:
    return json.dumps(
        [message.model_dump(mode="json") for message in messages], default=str
    )


def _row_to_conversation(row: Row) -> Conversation:
    return Conversation(
        id=str(row[0]),
        title=str(row[1]),
        knowledge_base_id=str(row[2]),
        messages=_decode_messages(row[3]),
        created_at=cast(datetime, row[4]),
        updated_at=cast(datetime, row[5]),
    )


def _decode_messages(raw: object) -> list[ConversationMessage]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ConversationPersistenceError(
            "conversations.messages did not decode to a list."
        )
    return [
        ConversationMessage.model_validate(item) for item in cast(list[object], raw)
    ]


__all__ = ["PostgresConversationRepository"]
