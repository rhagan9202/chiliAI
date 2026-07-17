"""Persisted timeseries anomaly points (BL-047, sprint 2026-28 B2).

Creates the timeseries_anomalies table written by the worker's timeseries
stage and read by the analytics entity-timeseries route.

Revision ID: 0011_timeseries_anomalies
Revises: 0010_event_dlq
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_timeseries_anomalies"
down_revision: str | None = "0010_event_dlq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE timeseries_anomalies (
            knowledge_base_id  text             NOT NULL,
            entity_id          text             NOT NULL,
            metric_name        text             NOT NULL,
            observed_at        timestamptz      NOT NULL,
            observed_value     double precision NOT NULL,
            expected_value     double precision NOT NULL,
            z_score            double precision NOT NULL,
            severity           double precision NOT NULL,
            detection_strategy text             NOT NULL,
            correlation_id     text             NOT NULL,
            detected_at        timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS timeseries_anomalies")
