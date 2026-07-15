"""Durable event dead-letter-queue records (BL-023, events.10).

Revision ID: 0010_event_dlq
Revises: 0009_document_status
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_event_dlq"
down_revision: str | None = "0009_document_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_dlq (
            dlq_id text PRIMARY KEY,
            event_type text NOT NULL,
            correlation_id text NOT NULL,
            payload jsonb NOT NULL,
            error_message text NOT NULL,
            error_traceback text NOT NULL,
            retry_count integer NOT NULL,
            failed_at timestamptz NOT NULL,
            status text NOT NULL DEFAULT 'pending',
            replayed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_event_dlq_status_created
        ON event_dlq (status, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_event_dlq_status_created")
    op.execute("DROP TABLE IF EXISTS event_dlq")
