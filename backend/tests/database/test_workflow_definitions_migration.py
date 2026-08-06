from __future__ import annotations

from pathlib import Path


def test_workflow_definition_snapshots_migration_declares_table() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "database/migrations/versions/0021_workflow_definition_snapshots.py"
    ).read_text(encoding="utf-8")

    assert "revision: str = \"0021_workflow_definitions\"" in migration
    assert "down_revision: str | None = \"0020_playbook_snapshot_kb_scope\"" in migration
    assert "CREATE TABLE IF NOT EXISTS workflow_definition_snapshots" in migration
    assert "snapshot_id text PRIMARY KEY" in migration
    assert (
        "UNIQUE (knowledge_base_id, definition_id, version)"
        in migration
    )
    assert "allowed_capability_refs jsonb NOT NULL" in migration
    assert "steps jsonb NOT NULL" in migration
    assert (
        "knowledge_base_id, status, updated_at DESC"
        in migration
    )
