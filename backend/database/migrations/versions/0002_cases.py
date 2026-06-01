"""Cases table for durable, KB-scoped case management (BL-010).

Adds the ``cases`` table backing ``cases.adapters.postgres.PostgresCaseRepository``.

Revision ID: 0002_cases
Revises: 0001_persistence_baseline
Create Date: 2026-06-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_cases"
down_revision: str | None = "0001_persistence_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cases (
            knowledge_base_id    text        NOT NULL,
            case_id              text        NOT NULL,
            title                text        NOT NULL,
            status               text        NOT NULL,
            priority             text        NOT NULL,
            assignee             text,
            originating_alert_id text,
            evidence_pack_id     text,
            alert_ids            jsonb       NOT NULL DEFAULT '[]'::jsonb,
            timeline             jsonb       NOT NULL DEFAULT '[]'::jsonb,
            created_at           timestamptz NOT NULL DEFAULT now(),
            updated_at           timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, case_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_cases_status "
        "ON cases (knowledge_base_id, status, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cases_status")
    op.execute("DROP TABLE IF EXISTS cases")
