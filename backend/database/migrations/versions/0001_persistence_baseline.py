"""Persistence baseline schema.

Creates the six persistence tables from
docs/superpowers/specs/2026-05-14-backend-persistence-design.md §6 and
converts the two time-series tables into TimescaleDB hypertables.

Revision ID: 0001_persistence_baseline
Revises:
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_persistence_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # --- ingestion: canonical tabular landing zone -------------------------
    op.execute(
        """
        CREATE TABLE raw_records (
            knowledge_base_id text        NOT NULL,
            record_type       text        NOT NULL,
            record_id         text        NOT NULL,
            payload           jsonb       NOT NULL,
            source_type       text        NOT NULL,
            source_ref        text,
            correlation_id    text        NOT NULL,
            content_hash      text        NOT NULL,
            ingested_at       timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, record_type, record_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_raw_records_payload ON raw_records USING gin (payload)")
    op.execute(
        "CREATE INDEX ix_raw_records_correlation "
        "ON raw_records (knowledge_base_id, correlation_id)"
    )

    # --- monitoring: scored observations (hypertable) ----------------------
    op.execute(
        """
        CREATE TABLE observations (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            entity_type       text             NOT NULL,
            metric_name       text             NOT NULL,
            score             double precision NOT NULL,
            observed_at       timestamptz      NOT NULL,
            rationale         text             NOT NULL,
            evidence_pack_id  text,
            batch_id          text             NOT NULL,
            correlation_id    text             NOT NULL,
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
        )
        """
    )
    op.execute("SELECT create_hypertable('observations', 'observed_at')")
    op.execute(
        "CREATE INDEX ix_observations_batch "
        "ON observations (knowledge_base_id, batch_id)"
    )

    # --- analytics: graph metrics over time (hypertable) -------------------
    op.execute(
        """
        CREATE TABLE entity_metric_history (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            metric_name       text             NOT NULL,
            value             double precision NOT NULL,
            observed_at       timestamptz      NOT NULL,
            correlation_id    text             NOT NULL,
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
        )
        """
    )
    op.execute("SELECT create_hypertable('entity_metric_history', 'observed_at')")

    # --- analytics: latest metric snapshot (data table) --------------------
    op.execute(
        """
        CREATE TABLE entity_metrics_current (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            metric_name       text             NOT NULL,
            value             double precision NOT NULL,
            updated_at        timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name)
        )
        """
    )

    # --- analytics: risk assessment history --------------------------------
    op.execute(
        """
        CREATE TABLE risk_score_history (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            request_id        text             NOT NULL,
            overall_score     double precision NOT NULL,
            risk_level        text             NOT NULL,
            factors           jsonb            NOT NULL,
            assessed_at       timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (request_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_risk_score_history_entity "
        "ON risk_score_history (knowledge_base_id, entity_id, assessed_at DESC)"
    )

    # --- monitoring: analytics-facing alert log ----------------------------
    op.execute(
        """
        CREATE TABLE alert_history (
            knowledge_base_id text        NOT NULL,
            alert_id          text        NOT NULL,
            entity_id         text        NOT NULL,
            entity_type       text        NOT NULL,
            severity          text        NOT NULL,
            status            text        NOT NULL,
            title             text        NOT NULL,
            reasoning         text        NOT NULL,
            metric_name       text        NOT NULL,
            evidence_pack_id  text,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, alert_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_alert_history_entity "
        "ON alert_history (knowledge_base_id, entity_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_history")
    op.execute("DROP TABLE IF EXISTS risk_score_history")
    op.execute("DROP TABLE IF EXISTS entity_metrics_current")
    op.execute("DROP TABLE IF EXISTS entity_metric_history")
    op.execute("DROP TABLE IF EXISTS observations")
    op.execute("DROP TABLE IF EXISTS raw_records")
