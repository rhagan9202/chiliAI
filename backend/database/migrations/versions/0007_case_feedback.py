"""Persist analyst feedback history on cases.

Revision ID: 0007_case_feedback
Revises: 0006_entity_derived_signals
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_case_feedback"
down_revision: str | None = "0006_entity_derived_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cases
        ADD COLUMN feedback_history jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS feedback_history")
