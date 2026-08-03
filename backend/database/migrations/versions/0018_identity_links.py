"""Add durable identity-link table.

Revision ID: 0018_identity_links
Revises: 0017_explanation_reviews
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op

revision: str = "0018_identity_links"
down_revision: str | None = "0017_explanation_reviews"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS identity_links (
            id text NOT NULL,
            knowledge_base_id text NOT NULL,
            canonical_entity_id text NOT NULL,
            source_entity_id text NOT NULL,
            relationship_type text NOT NULL,
            confidence text NOT NULL,
            score double precision NOT NULL,
            review_state text NOT NULL,
            decision_source text NOT NULL,
            source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
            match_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
            decision_history jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_identity_links_confidence CHECK (
                confidence IN ('high', 'medium', 'low')
            ),
            CONSTRAINT ck_identity_links_score CHECK (score >= 0 AND score <= 1),
            CONSTRAINT ck_identity_links_review_state CHECK (
                review_state IN (
                    'auto_linkable',
                    'steward_review',
                    'needs_review',
                    'merged',
                    'rejected',
                    'split'
                )
            ),
            CONSTRAINT ck_identity_links_decision_history_type CHECK (
                jsonb_typeof(decision_history) = 'array'
            ),
            CONSTRAINT pk_identity_links PRIMARY KEY (knowledge_base_id, id),
            CONSTRAINT ck_identity_links_decision_history_values CHECK (
                decision_history = '[]'::jsonb
                OR (
                    jsonb_array_length(
                        jsonb_path_query_array(decision_history, '$[*].decision')
                    ) = jsonb_array_length(decision_history)
                    AND jsonb_path_query_array(
                        decision_history,
                        '$[*].decision'
                    ) <@ '[
                        "approve_merge",
                        "reject_merge",
                        "split_identity"
                    ]'::jsonb
                )
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_identity_links_kb_canonical_updated
        ON identity_links (knowledge_base_id, canonical_entity_id, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_identity_links_kb_source_updated
        ON identity_links (knowledge_base_id, source_entity_id, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_identity_links_kb_review_state_updated
        ON identity_links (knowledge_base_id, review_state, updated_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_identity_links_kb_review_state_updated")
    op.execute("DROP INDEX IF EXISTS ix_identity_links_kb_source_updated")
    op.execute("DROP INDEX IF EXISTS ix_identity_links_kb_canonical_updated")
    op.execute("DROP TABLE IF EXISTS identity_links")
