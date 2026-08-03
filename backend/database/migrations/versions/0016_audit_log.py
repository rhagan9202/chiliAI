"""Add durable audit-log ledger table.

Revision ID: 0016_audit_log
Revises: 0015_alert_generation_metadata
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op

revision: str = "0016_audit_log"
down_revision: str | None = "0015_alert_generation_metadata"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            event_id text PRIMARY KEY,
            occurred_at timestamptz NOT NULL,
            tenant_id text NOT NULL,
            knowledge_base_id text,
            actor_user_id text NOT NULL,
            actor_email text,
            actor_roles jsonb NOT NULL DEFAULT '[]'::jsonb,
            action text NOT NULL,
            resource_type text NOT NULL,
            resource_id text NOT NULL,
            "before" jsonb,
            "after" jsonb,
            correlation_id text NOT NULL,
            client_ip text,
            user_agent text,
            outcome text NOT NULL,
            failure_reason text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_audit_log_outcome CHECK (outcome IN ('success', 'failure'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_log_tenant_occurred_at
        ON audit_log (tenant_id, occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_log_kb_occurred_at
        ON audit_log (knowledge_base_id, occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_log_actor_occurred_at
        ON audit_log (actor_user_id, occurred_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_log_actor_occurred_at")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_kb_occurred_at")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_tenant_occurred_at")
    op.execute("DROP TABLE IF EXISTS audit_log")
