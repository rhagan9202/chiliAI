"""Add workflow definition snapshots.

Revision ID: 0021_workflow_definitions
Revises: 0020_playbook_snapshot_kb_scope
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op

revision: str = "0021_workflow_definitions"
down_revision: str | None = "0020_playbook_snapshot_kb_scope"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_definition_snapshots (
            snapshot_id text PRIMARY KEY,
            knowledge_base_id text NOT NULL,
            domain_name text,
            definition_id text NOT NULL,
            version text NOT NULL,
            status text NOT NULL,
            name text NOT NULL,
            description text,
            allowed_capability_refs jsonb NOT NULL,
            steps jsonb NOT NULL,
            created_by text NOT NULL,
            approved_by text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            approved_at timestamptz,
            retired_at timestamptz,
            CONSTRAINT uq_workflow_definition_snapshots_natural_key
                UNIQUE (knowledge_base_id, definition_id, version),
            CONSTRAINT ck_workflow_definition_snapshots_status CHECK (
                status IN ('draft', 'approved', 'retired')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_definition_snapshots_kb_status
        ON workflow_definition_snapshots (
            knowledge_base_id, status, updated_at DESC
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_definition_snapshots_kb_status")
    op.execute("DROP TABLE IF EXISTS workflow_definition_snapshots")
