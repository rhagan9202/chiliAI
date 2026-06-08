"""Derived peer-group z-score risk signals.

Creates the entity_derived_signals table consumed by PostgresRiskSignalSource.

Revision ID: 0006_entity_derived_signals
Revises: 0005_conversations
Create Date: 2026-06-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_entity_derived_signals"
down_revision: str | None = "0005_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE entity_derived_signals (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            entity_type       text             NOT NULL,
            metric_name       text             NOT NULL,
            interval_start    timestamptz      NOT NULL,
            peer_group_key    text             NOT NULL,
            aggregate_value   double precision NOT NULL,
            peer_mean         double precision NOT NULL,
            peer_std          double precision NOT NULL,
            z_score           double precision NOT NULL,
            signal_value      double precision NOT NULL,
            weight            double precision NOT NULL,
            rationale         text             NOT NULL,
            correlation_id    text             NOT NULL,
            computed_at       timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, interval_start)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_entity_derived_signals_latest "
        "ON entity_derived_signals "
        "(knowledge_base_id, entity_id, metric_name, computed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS entity_derived_signals")
