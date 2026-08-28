"""Index alert_history by alert_id for the unscoped detail read.

``_ALERT_GET_SQL`` and ``_ALERT_ACK_SQL`` match on ``alert_id`` alone, but
every existing index leads with ``knowledge_base_id``, so both sequentially
scan. UNIQUE rather than a plain index because the adapter's own comment
already assumes global uniqueness ("a UUID minted upstream and globally unique
in practice") -- this enforces the assumption instead of restating it.

Revision ID: 0029_alert_history_alert_id_ix
Revises: 0028_derived_signal_interval_ix
"""

from __future__ import annotations

from alembic import op

revision: str = "0029_alert_history_alert_id_ix"
down_revision: str | None = "0028_derived_signal_interval_ix"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX ix_alert_history_alert_id ON alert_history (alert_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_alert_history_alert_id")
