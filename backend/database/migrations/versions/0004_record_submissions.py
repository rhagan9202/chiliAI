"""Submission-level dedup table for records ingestion (BL-015).

Backs the ``was_submitted`` / ``record_submission`` methods on
``records.adapters.postgres.PostgresRawRecordStore``.

Revision ID: 0004_record_submissions
Revises: 0003_policy
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_record_submissions"
down_revision: str | None = "0003_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE record_submissions (
            knowledge_base_id text        NOT NULL,
            submission_hash   text        NOT NULL,
            correlation_id    text        NOT NULL,
            created_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, submission_hash)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS record_submissions")
