"""Add durable explanation-review table.

Revision ID: 0017_explanation_reviews
Revises: 0016_audit_log
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op

revision: str = "0017_explanation_reviews"
down_revision: str | None = "0016_audit_log"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS explanation_reviews (
            id text PRIMARY KEY,
            knowledge_base_id text NOT NULL,
            evidence_pack_id text NOT NULL,
            target_type text NOT NULL,
            target_id text NOT NULL,
            state text NOT NULL,
            reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            comment text,
            actor_user_id text NOT NULL,
            actor_email text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            update_count integer NOT NULL DEFAULT 0,
            CONSTRAINT uq_explanation_reviews_target UNIQUE (
                knowledge_base_id,
                evidence_pack_id,
                target_type,
                target_id
            ),
            CONSTRAINT ck_explanation_reviews_target_type CHECK (
                target_type IN (
                    'narrative',
                    'narrative_section',
                    'feature_attribution',
                    'evidence_item',
                    'provenance_reference'
                )
            ),
            CONSTRAINT ck_explanation_reviews_state CHECK (
                state IN (
                    'useful',
                    'incomplete',
                    'misleading',
                    'unsupported',
                    'approved',
                    'rejected',
                    'regeneration_requested'
                )
            ),
            CONSTRAINT ck_explanation_reviews_update_count CHECK (update_count >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_explanation_reviews_kb_pack_updated
        ON explanation_reviews (knowledge_base_id, evidence_pack_id, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_explanation_reviews_kb_state_updated
        ON explanation_reviews (knowledge_base_id, state, updated_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_explanation_reviews_kb_state_updated")
    op.execute("DROP INDEX IF EXISTS ix_explanation_reviews_kb_pack_updated")
    op.execute("DROP TABLE IF EXISTS explanation_reviews")
