"""Durable per-document ingestion status projection (BL-041).

Revision ID: 0009_document_status
Revises: 0008_scorecards
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_document_status"
down_revision: str | None = "0008_scorecards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_document_status (
            knowledge_base_id text NOT NULL,
            source_document_id text NOT NULL,
            current_status text NOT NULL,
            status_rank integer NOT NULL,
            last_error text,
            dropped_entity_count integer NOT NULL DEFAULT 0,
            dropped_relationship_count integer NOT NULL DEFAULT 0,
            sample_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            first_event_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (knowledge_base_id, source_document_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_source_document_status_kb_status
        ON source_document_status (knowledge_base_id, current_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_source_document_status_kb_status")
    op.execute("DROP TABLE IF EXISTS source_document_status")
