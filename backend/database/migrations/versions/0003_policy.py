"""Policy items table for durable, KB-scoped policy intelligence (BL-011).

Backs ``policy.adapters.postgres.PostgresPolicyItemRepository``.

Revision ID: 0003_policy
Revises: 0002_cases
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_policy"
down_revision: str | None = "0002_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE policy_items (
            knowledge_base_id text        NOT NULL,
            rule_id           text        NOT NULL,
            target_ref        text        NOT NULL,
            item_id           text        NOT NULL,
            rule_pack_id      text        NOT NULL,
            target_kind       text        NOT NULL,
            title             text        NOT NULL,
            severity          text        NOT NULL,
            matched_fields    jsonb       NOT NULL DEFAULT '{}'::jsonb,
            citations         jsonb       NOT NULL DEFAULT '[]'::jsonb,
            status            text        NOT NULL,
            disposition       jsonb,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, rule_id, target_ref)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_policy_items_item_id "
        "ON policy_items (knowledge_base_id, item_id)"
    )
    op.execute(
        "CREATE INDEX ix_policy_items_status "
        "ON policy_items (knowledge_base_id, status, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_policy_items_status")
    op.execute("DROP INDEX IF EXISTS ux_policy_items_item_id")
    op.execute("DROP TABLE IF EXISTS policy_items")
