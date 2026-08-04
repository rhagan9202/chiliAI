"""Add fraud playbook snapshots.

Revision ID: 0019_fraud_playbooks
Revises: 0018_identity_links
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op

revision: str = "0019_fraud_playbooks"
down_revision: str | None = "0018_identity_links"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fraud_playbook_snapshots (
            domain_name text NOT NULL,
            playbook_id text NOT NULL,
            version text NOT NULL,
            status text NOT NULL,
            definition jsonb NOT NULL,
            source text NOT NULL,
            published_by text NOT NULL,
            published_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT pk_fraud_playbook_snapshots
                PRIMARY KEY (domain_name, playbook_id, version),
            CONSTRAINT ck_fraud_playbook_snapshots_status CHECK (
                status IN ('draft', 'published', 'retired')
            ),
            CONSTRAINT ck_fraud_playbook_snapshots_source CHECK (
                source IN ('domain_config', 'api_import', 'api_publish')
            )
        )
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
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS playbook_ref jsonb
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS playbook_ref")
    op.execute("DROP INDEX IF EXISTS ix_fraud_playbook_snapshots_domain_status")
    op.execute("DROP TABLE IF EXISTS fraud_playbook_snapshots")
