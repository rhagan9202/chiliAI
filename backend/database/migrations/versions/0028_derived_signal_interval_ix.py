"""Re-point the derived-signal freshness index at interval_start.

``PostgresRiskSignalSource.load_profile`` picks the newest signal per metric
with ``DISTINCT ON (metric_name) ... ORDER BY metric_name, interval_start DESC,
computed_at DESC``. The 0006 index stopped at ``computed_at``, which no longer
matches that ordering, so the lookup degraded to a sort of every row for the
entity on a path that runs for each scored entity.

``computed_at`` is kept as the trailing tie-break column so the index still
serves the full ordering.

Revision ID: 0028_derived_signal_interval_ix
Revises: 0027_score_run_skipped_entities
"""

from __future__ import annotations

from alembic import op

revision: str = "0028_derived_signal_interval_ix"
down_revision: str | None = "0027_score_run_skipped_entities"
branch_labels: None = None
depends_on: None = None

_OLD_INDEX = (
    "ON entity_derived_signals "
    "(knowledge_base_id, entity_id, metric_name, computed_at DESC)"
)
_NEW_INDEX = (
    "ON entity_derived_signals "
    "(knowledge_base_id, entity_id, metric_name, interval_start DESC, computed_at DESC)"
)


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entity_derived_signals_latest")
    op.execute(f"CREATE INDEX ix_entity_derived_signals_latest {_NEW_INDEX}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entity_derived_signals_latest")
    op.execute(f"CREATE INDEX ix_entity_derived_signals_latest {_OLD_INDEX}")
