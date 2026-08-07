"""Index connector sync runs for stale reconciliation.

Revision ID: 0026_connector_sync_stale_index
Revises: 0025_connectors
Create Date: 2026-08-07

The reconciler scans for runs in a set of statuses not updated since a cutoff,
across every knowledge base. `ix_connector_sync_runs_connector_status` is
`(connector_id, status, started_at DESC)` — it leads with `connector_id`, which
the sweep does not filter on, so it cannot serve that scan. Without this index
the sweep is a sequential scan of every sync run ever recorded, on a timer.

`started_at` is also the wrong column: a run's *progress* is `updated_at`, which
the executor stamps on every page. `started_at` never moves, so a long-running
healthy run and a stalled one look identical by it.
"""

from __future__ import annotations

from alembic import op

revision: str = "0026_connector_sync_stale_index"
down_revision: str | None = "0025_connectors"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connector_sync_runs_status_updated
        ON connector_sync_runs (status, updated_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_connector_sync_runs_status_updated")
