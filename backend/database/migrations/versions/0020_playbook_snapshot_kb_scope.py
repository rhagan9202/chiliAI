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
    # The upgrade widened uniqueness to include knowledge_base_id, so a
    # populated database can legitimately hold one row per knowledge base for
    # the same (domain_name, playbook_id, version) -- the pre-0020 schema has
    # no column to disambiguate those rows. Silently deleting the extras to
    # force the narrower PRIMARY KEY back on would destroy playbook
    # snapshots the playbooks module treats as immutable published history,
    # with no visible signal beyond a clean exit code. Fail loudly instead so
    # an operator resolves the duplicates deliberately before retrying.
    op.execute(
        """
        DO $$
        DECLARE
            duplicate_count integer;
        BEGIN
            SELECT count(*) INTO duplicate_count
            FROM (
                SELECT domain_name, playbook_id, version
                FROM fraud_playbook_snapshots
                GROUP BY domain_name, playbook_id, version
                HAVING count(*) > 1
            ) AS duplicated_keys;

            IF duplicate_count > 0 THEN
                RAISE EXCEPTION
                    'Cannot downgrade fraud_playbook_snapshots: % '
                    '(domain_name, playbook_id, version) group(s) hold '
                    'snapshots from more than one knowledge_base_id. The '
                    'pre-0020 schema cannot represent per-knowledge-base '
                    'snapshots. Resolve the duplicates manually (export, '
                    'reassign, or delete the extra knowledge_base_id rows) '
                    'before retrying this downgrade.',
                    duplicate_count;
            END IF;
        END $$;
        """
    )
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
