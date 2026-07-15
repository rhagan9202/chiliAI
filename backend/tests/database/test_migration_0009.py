"""Unit checks for the 0009 source_document_status migration (no DB needed)."""

from __future__ import annotations

from importlib import import_module

import pytest

_MODULE = "database.migrations.versions.0009_document_status"


def test_revision_chain() -> None:
    migration = import_module(_MODULE)
    assert migration.revision == "0009_document_status"
    assert migration.down_revision == "0008_scorecards"


def test_upgrade_creates_source_document_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module(_MODULE)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.upgrade()
    normalized = " ".join(" ".join(statements).split()).lower()
    assert "create table if not exists source_document_status" in normalized
    assert "primary key (knowledge_base_id, source_document_id)" in normalized
    assert "current_status text not null" in normalized
    assert "status_rank integer not null" in normalized
    assert "last_error text" in normalized
    assert "sample_reasons jsonb not null default '[]'::jsonb" in normalized
    assert "ix_source_document_status_kb_status" in normalized


def test_downgrade_drops_table(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = import_module(_MODULE)
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.downgrade()
    joined = " ".join(statements).lower()
    assert "drop index if exists ix_source_document_status_kb_status" in joined
    assert "drop table if exists source_document_status" in joined
