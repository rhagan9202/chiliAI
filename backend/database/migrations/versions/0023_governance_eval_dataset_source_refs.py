"""Add governance eval dataset source refs.

Revision ID: 0023_eval_dataset_refs
Revises: 0022_governance_eval_runs
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op

revision: str = "0023_eval_dataset_refs"
down_revision: str | None = "0022_governance_eval_runs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE governance_eval_runs
        ADD COLUMN IF NOT EXISTS dataset_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE governance_eval_runs
        DROP COLUMN IF EXISTS dataset_source_refs
        """
    )
