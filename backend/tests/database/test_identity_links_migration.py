"""Tests for the SAFE-CMS-012 identity-link migration."""

from __future__ import annotations

from importlib import import_module

import pytest

_MIGRATION = "database.migrations.versions.0018_identity_links"


def test_identity_links_migration_declares_table_constraints_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module(_MIGRATION)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    sql = " ".join(statements).lower()
    assert "create table if not exists identity_links" in sql
    assert "decision_history jsonb not null default '[]'::jsonb" in sql
    assert "ck_identity_links_review_state" in sql
    assert "approve_merge" in sql
    assert "ix_identity_links_kb_canonical_updated" in sql
    assert "ix_identity_links_kb_source_updated" in sql
