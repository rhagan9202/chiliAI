"""Alert history read-model columns (alerts feed served from Postgres).

Revision ID: 0012_alert_history_read_model
Revises: 0011_timeseries_anomalies
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_alert_history_read_model"
down_revision: str | None = "0011_timeseries_anomalies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE alert_history
        ADD COLUMN entity_label text NOT NULL DEFAULT '',
        ADD COLUMN confidence double precision NOT NULL DEFAULT 0,
        ADD COLUMN tags jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE alert_history
        DROP COLUMN IF EXISTS tags,
        DROP COLUMN IF EXISTS confidence,
        DROP COLUMN IF EXISTS entity_label
        """
    )
