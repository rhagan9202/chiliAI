"""Unit checks for the 0006 entity_derived_signals migration (no DB needed)."""

from __future__ import annotations

from importlib import import_module

import pytest

_MODULE = "database.migrations.versions.0006_entity_derived_signals"


def test_revision_chain() -> None:
    migration = import_module(_MODULE)
    assert migration.revision == "0006_entity_derived_signals"
    assert migration.down_revision == "0005_conversations"


def test_upgrade_creates_entity_derived_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module(_MODULE)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()
    normalized = " ".join(statements).lower()
    assert "create table entity_derived_signals" in normalized
    assert (
        "primary key (knowledge_base_id, entity_id, metric_name, interval_start)"
        in normalized
    )
    assert "ix_entity_derived_signals_latest" in normalized


def test_downgrade_drops_table(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module(_MODULE)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.downgrade()
    joined = " ".join(statements).lower()
    assert "drop table" in joined
    assert "entity_derived_signals" in joined
