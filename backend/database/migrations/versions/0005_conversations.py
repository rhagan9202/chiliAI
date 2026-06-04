"""Conversations table for durable RAG chat persistence (BL-012).

Backs ``conversations.adapters.postgres.PostgresConversationRepository``.

Revision ID: 0005_conversations
Revises: 0004_record_submissions
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_conversations"
down_revision: str | None = "0004_record_submissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            conversation_id   text        NOT NULL,
            title             text        NOT NULL,
            knowledge_base_id text        NOT NULL,
            messages          jsonb       NOT NULL DEFAULT '[]'::jsonb,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (conversation_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_conversations_kb "
        "ON conversations (knowledge_base_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_conversations_kb")
    op.execute("DROP TABLE IF EXISTS conversations")
