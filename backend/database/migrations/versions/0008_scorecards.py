"""Persist generated scorecard runs.

Revision ID: 0008_scorecards
Revises: 0007_case_feedback
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_scorecards"
down_revision: str | None = "0007_case_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scorecard_runs (
            knowledge_base_id text NOT NULL,
            run_id text NOT NULL,
            template_id text NOT NULL,
            template_name text NOT NULL,
            scope_type text NOT NULL,
            scope_id text NOT NULL,
            period_start date NOT NULL,
            period_end date NOT NULL,
            source_snapshot_hash text NOT NULL,
            status text NOT NULL,
            overall_health text NOT NULL,
            sections jsonb NOT NULL,
            export_payloads jsonb NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (knowledge_base_id, run_id),
            UNIQUE (
                knowledge_base_id,
                template_id,
                scope_type,
                scope_id,
                period_start,
                period_end,
                source_snapshot_hash
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scorecard_runs_kb_template
        ON scorecard_runs (knowledge_base_id, template_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scorecard_runs_kb_template")
    op.execute("DROP TABLE IF EXISTS scorecard_runs")
