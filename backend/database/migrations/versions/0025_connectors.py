"""Add connector definitions, sync runs, and quarantined source records.

Revision ID: 0025_connectors
Revises: 0024_score_runs
Create Date: 2026-08-07

Connectors and their sync runs were in-memory only, so every registered
connector and every sync run vanished on API restart. This is the durable
half of making `POST /knowledgebases/{kb}/connectors/{id}/sync-runs` mean
something: the executor claims a run row, advances `source_cursor` page by
page, and a crash resumes from the cursor instead of restarting the pull.

Columns mirror `connectors/models.py` exactly. `domain_name` and
`schedule_expression` are carried explicitly rather than folded into
`config`, because they are typed fields on `ConnectorDefinition` and a
round trip through this table must return the definition that was saved.
"""

from __future__ import annotations

from alembic import op

revision: str = "0025_connectors"
down_revision: str | None = "0024_score_runs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connectors (
            connector_id text NOT NULL,
            knowledge_base_id text NOT NULL,
            name text NOT NULL,
            source_type text NOT NULL,
            domain_name text,
            status text NOT NULL,
            schedule_mode text NOT NULL,
            schedule_expression text,
            credentials_ref text,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            -- Composite, not `connector_id` alone. The repository protocol is
            -- KB-scoped (`get_definition(*, knowledge_base_id, connector_id)`)
            -- and the in-memory adapter keys on the pair, so a global primary
            -- key would let the two backends disagree: the same connector id
            -- in two knowledge bases works in memory and silently fails to
            -- store in Postgres.
            CONSTRAINT pk_connectors PRIMARY KEY (knowledge_base_id, connector_id),
            CONSTRAINT ck_connectors_source_type CHECK (
                source_type IN ('filesystem', 'object_store', 'http')
            ),
            CONSTRAINT ck_connectors_status CHECK (
                status IN ('active', 'disabled')
            ),
            CONSTRAINT ck_connectors_schedule_mode CHECK (
                schedule_mode IN ('manual', 'interval', 'cron')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connectors_kb
        ON connectors (knowledge_base_id, status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_sync_runs (
            run_id text PRIMARY KEY,
            connector_id text NOT NULL,
            knowledge_base_id text NOT NULL,
            requested_by text NOT NULL,
            status text NOT NULL,
            counters jsonb NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key text,
            ingest_correlation_id text,
            source_cursor text,
            error_message text,
            started_at timestamptz NOT NULL,
            completed_at timestamptz,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_connector_sync_runs_status CHECK (
                status IN ('queued', 'running', 'completed', 'failed', 'canceled')
            ),
            CONSTRAINT fk_connector_sync_runs_connector
                FOREIGN KEY (knowledge_base_id, connector_id)
                REFERENCES connectors (knowledge_base_id, connector_id)
                ON DELETE CASCADE
        )
        """
    )
    # Partial unique index rather than a service-side read-then-write: two
    # concurrent sync requests carrying the same key must not both insert.
    #
    # Scoped by knowledge base as well as connector, matching the service's own
    # lookup (`list_runs(connector_id=..., knowledge_base_id=...)`). Without the
    # knowledge_base_id the two disagree: connectors are KB-scoped, so the same
    # connector id in two knowledge bases would share one idempotency namespace
    # and the second KB's first sync would be rejected as a duplicate.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_connector_sync_runs_idempotency
        ON connector_sync_runs (knowledge_base_id, connector_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connector_sync_runs_connector_status
        ON connector_sync_runs (connector_id, status, started_at DESC)
        """
    )
    # Invalid source rows are quarantined, not dropped: the run counters say
    # how many, and this table says which ones and why.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_quarantine_records (
            quarantine_id text PRIMARY KEY,
            run_id text NOT NULL
                REFERENCES connector_sync_runs(run_id) ON DELETE CASCADE,
            connector_id text NOT NULL,
            knowledge_base_id text NOT NULL,
            source_record_id text NOT NULL,
            reason text NOT NULL,
            raw_ref text,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connector_quarantine_run
        ON connector_quarantine_records (run_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connector_quarantine_connector
        ON connector_quarantine_records (connector_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_connector_quarantine_connector")
    op.execute("DROP INDEX IF EXISTS ix_connector_quarantine_run")
    op.execute("DROP TABLE IF EXISTS connector_quarantine_records")
    op.execute("DROP INDEX IF EXISTS ix_connector_sync_runs_connector_status")
    op.execute("DROP INDEX IF EXISTS ux_connector_sync_runs_idempotency")
    op.execute("DROP TABLE IF EXISTS connector_sync_runs")
    op.execute("DROP INDEX IF EXISTS ix_connectors_kb")
    op.execute("DROP TABLE IF EXISTS connectors")
