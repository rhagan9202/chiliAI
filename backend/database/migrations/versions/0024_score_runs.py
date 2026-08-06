"""Add durable score-all run tracking.

Score runs and their batches were in-memory only, so a run vanished on API
restart mid-execution and `replay_failed_batches` had nothing to replay.

Revision ID: 0024_score_runs
Revises: 0023_eval_dataset_refs
Create Date: 2026-08-06
"""

from __future__ import annotations

from alembic import op

revision: str = "0024_score_runs"
down_revision: str | None = "0023_eval_dataset_refs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS score_runs (
            id text PRIMARY KEY,
            knowledge_base_id text NOT NULL,
            status text NOT NULL,
            requested_by text,
            idempotency_key text,
            model_version text NOT NULL,
            catalog_version text NOT NULL,
            replay_of_run_id text,
            entity_cursor text,
            total_entities integer NOT NULL DEFAULT 0,
            scored_entities integer NOT NULL DEFAULT 0,
            failed_entities integer NOT NULL DEFAULT 0,
            error_summary text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            CONSTRAINT ck_score_runs_status CHECK (
                status IN (
                    'queued', 'running', 'completed',
                    'failed', 'canceled', 'replayed'
                )
            )
        )
        """
    )
    # Idempotency is enforced here rather than by a read-then-write in the
    # service: two concurrent starts with the same key would both find nothing
    # and both insert.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_score_runs_kb_idempotency
        ON score_runs (knowledge_base_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_score_runs_kb_status
        ON score_runs (knowledge_base_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS score_batches (
            id text PRIMARY KEY,
            run_id text NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE,
            knowledge_base_id text NOT NULL,
            batch_number integer NOT NULL,
            status text NOT NULL,
            entity_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            attempts integer NOT NULL DEFAULT 0,
            error_summary text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            CONSTRAINT ck_score_batches_status CHECK (
                status IN (
                    'queued', 'running', 'completed',
                    'failed', 'canceled', 'replayed'
                )
            ),
            UNIQUE (run_id, batch_number)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_score_batches_run_status
        ON score_batches (run_id, status, batch_number)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_score_batches_run_status")
    op.execute("DROP TABLE IF EXISTS score_batches")
    op.execute("DROP INDEX IF EXISTS ix_score_runs_kb_status")
    op.execute("DROP INDEX IF EXISTS ux_score_runs_kb_idempotency")
    op.execute("DROP TABLE IF EXISTS score_runs")
