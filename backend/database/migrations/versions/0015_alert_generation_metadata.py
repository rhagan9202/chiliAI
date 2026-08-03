"""Persist alert generation metadata for queue review.

Revision ID: 0015_alert_generation_metadata
Revises: 0014_alert_triage_operations
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op

revision: str = "0015_alert_generation_metadata"
down_revision: str | None = "0014_alert_triage_operations"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE alert_history
        ADD COLUMN generation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE alert_history
        DROP COLUMN IF EXISTS generation_metadata
        """
    )
