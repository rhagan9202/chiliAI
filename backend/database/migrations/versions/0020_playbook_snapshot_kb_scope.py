"""Scope fraud playbook snapshots by knowledge base.

Revision ID: 0020_playbook_snapshot_kb_scope
Revises: 0019_fraud_playbooks
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op

revision: str = "0020_playbook_snapshot_kb_scope"
down_revision: str | None = "0019_fraud_playbooks"
branch_labels: str | None = None
depends_on: str | None = None

_DEFAULT_KNOWLEDGE_BASE_ID = "__legacy__"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE fraud_playbook_snapshots
        ADD COLUMN IF NOT EXISTS knowledge_base_id text NOT NULL
            DEFAULT '{_DEFAULT_KNOWLEDGE_BASE_ID}'
        """
    )
    op.execute(
        """
        ALTER TABLE fraud_playbook_snapshots
        DROP CONSTRAINT IF EXISTS pk_fraud_playbook_snapshots
        """
    )
    op.execute(
        """
        ALTER TABLE fraud_playbook_snapshots
        ADD CONSTRAINT pk_fraud_playbook_snapshots
            PRIMARY KEY (knowledge_base_id, domain_name, playbook_id, version)
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_fraud_playbook_snapshots_domain_status")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fraud_playbook_snapshots_domain_status
        ON fraud_playbook_snapshots (
            knowledge_base_id, domain_name, status, updated_at DESC
        )
        """
    )
    op.execute(
        """
        ALTER TABLE fraud_playbook_snapshots
        ALTER COLUMN knowledge_base_id DROP DEFAULT
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fraud_playbook_snapshots_domain_status")
    op.execute(
        """
        ALTER TABLE fraud_playbook_snapshots
        DROP CONSTRAINT IF EXISTS pk_fraud_playbook_snapshots
        """
    )
    op.execute(
        """
        ALTER TABLE fraud_playbook_snapshots
        ADD CONSTRAINT pk_fraud_playbook_snapshots
            PRIMARY KEY (domain_name, playbook_id, version)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fraud_playbook_snapshots_domain_status
        ON fraud_playbook_snapshots (domain_name, status, updated_at DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE fraud_playbook_snapshots
        DROP COLUMN IF EXISTS knowledge_base_id
        """
    )
