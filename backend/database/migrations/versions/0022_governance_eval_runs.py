"""Add governance evaluation runs.

Revision ID: 0022_governance_eval_runs
Revises: 0021_workflow_definitions
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op

revision: str = "0022_governance_eval_runs"
down_revision: str | None = "0021_workflow_definitions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS governance_eval_runs (
            run_id text PRIMARY KEY,
            knowledge_base_id text NOT NULL,
            artifact_kind text NOT NULL,
            artifact_id text NOT NULL,
            artifact_version text NOT NULL,
            baseline_version text NOT NULL,
            dataset_id text NOT NULL,
            status text NOT NULL,
            metrics jsonb NOT NULL,
            drift_summary jsonb NOT NULL,
            dataset_source_refs jsonb NOT NULL,
            affected_alert_ids jsonb NOT NULL,
            affected_case_ids jsonb NOT NULL,
            created_by text NOT NULL,
            created_at timestamptz NOT NULL,
            approval jsonb,
            CONSTRAINT ck_governance_eval_runs_artifact_kind CHECK (
                artifact_kind IN (
                    'connector',
                    'model',
                    'playbook',
                    'prompt',
                    'scoring',
                    'workflow_definition'
                )
            ),
            CONSTRAINT ck_governance_eval_runs_status CHECK (
                status IN ('candidate', 'approved', 'rejected')
            )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE governance_eval_runs
        ADD COLUMN IF NOT EXISTS dataset_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_governance_eval_runs_kb_status
        ON governance_eval_runs (knowledge_base_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_governance_eval_runs_artifact
        ON governance_eval_runs (
            knowledge_base_id, artifact_kind, artifact_id, artifact_version
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_governance_eval_runs_artifact")
    op.execute("DROP INDEX IF EXISTS ix_governance_eval_runs_kb_status")
    op.execute("DROP TABLE IF EXISTS governance_eval_runs")
