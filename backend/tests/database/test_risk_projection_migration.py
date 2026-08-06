"""Migration shape tests for risk projection persistence."""

from __future__ import annotations

from importlib import import_module

import pytest


def test_risk_projection_migration_creates_projection_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("database.migrations.versions.0013_risk_projections")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    normalized = " ".join(statements).lower()
    assert "create table risk_projections" in normalized
    assert "primary key (knowledge_base_id, entity_id)" in normalized
    assert "top_typology_ids" in normalized
    assert "default '[]'::jsonb" in normalized
    assert "ix_risk_projections_kb_status" in normalized
    assert "ix_risk_projections_kb_score" in normalized


def test_risk_projection_migration_downgrade_drops_projection_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("database.migrations.versions.0013_risk_projections")
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert "DROP TABLE IF EXISTS risk_projections" in statements
