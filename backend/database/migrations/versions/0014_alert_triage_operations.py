"""Alert assignment and triage audit fields for SAFE-CMS-006.

Revision ID: 0014_alert_triage_operations
Revises: 0013_risk_projections
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_alert_triage_operations"
down_revision: str | None = "0013_risk_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE alert_history
        ADD COLUMN assignee text,
        ADD COLUMN triage_history jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        "CREATE INDEX ix_alert_history_kb_assignee "
        "ON alert_history (knowledge_base_id, assignee, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alert_history_kb_assignee")
    op.execute(
        """
        ALTER TABLE alert_history
        DROP COLUMN IF EXISTS triage_history,
        DROP COLUMN IF EXISTS assignee
        """
    )
