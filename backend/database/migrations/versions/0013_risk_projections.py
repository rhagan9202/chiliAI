"""Persisted risk projection read models for SAFE-CMS-003.

Revision ID: 0013_risk_projections
Revises: 0012_alert_history_read_model
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_risk_projections"
down_revision: str | None = "0012_alert_history_read_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE risk_projections (
            knowledge_base_id   text             NOT NULL,
            entity_id           text             NOT NULL,
            entity_type         text             NOT NULL,
            overall_score       double precision NOT NULL,
            risk_level          text             NOT NULL,
            top_typology_ids    jsonb            NOT NULL DEFAULT '[]'::jsonb,
            alert_ids           jsonb            NOT NULL DEFAULT '[]'::jsonb,
            case_ids            jsonb            NOT NULL DEFAULT '[]'::jsonb,
            evidence_pack_ids   jsonb            NOT NULL DEFAULT '[]'::jsonb,
            score_run_id        text,
            model_version       text             NOT NULL,
            catalog_version     text             NOT NULL,
            scored_at           timestamptz      NOT NULL,
            updated_at          timestamptz      NOT NULL,
            status              text             NOT NULL,
            PRIMARY KEY (knowledge_base_id, entity_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_risk_projections_kb_status "
        "ON risk_projections (knowledge_base_id, status, risk_level)"
    )
    op.execute(
        "CREATE INDEX ix_risk_projections_kb_score "
        "ON risk_projections (knowledge_base_id, overall_score DESC, scored_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS risk_projections")
