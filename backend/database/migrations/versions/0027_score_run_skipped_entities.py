"""Separate skipped entities from failed ones on score runs and batches.

Revision ID: 0027_score_run_skipped_entities
Revises: 0026_connector_sync_stale_index
Create Date: 2026-08-08

`failed_entities` was computed as `len(entity_ids) - scored`, so it absorbed
every entity the risk service *declined* to score — `RiskInsufficientSignalsError`,
which the executor catches and logs at INFO as an expected per-entity condition.
A live run over a knowledge base whose entities carry fewer than two signals
reported `completed, scored=0, failed=57` with no error message on any batch:
nothing had failed, and the only explanation lived in worker logs.

Backfill deliberately leaves existing rows at 0 rather than guessing. The
historical split between "failed" and "skipped" was never recorded, so any
redistribution would be invention; old runs keep reporting what they always
reported, and only new runs carry the distinction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0027_score_run_skipped_entities"
down_revision: str | None = "0026_connector_sync_stale_index"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("score_runs", "score_batches"):
        op.add_column(
            table,
            sa.Column(
                "skipped_entities",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    for table in ("score_batches", "score_runs"):
        op.drop_column(table, "skipped_entities")
