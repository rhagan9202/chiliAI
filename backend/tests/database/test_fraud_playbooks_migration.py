from __future__ import annotations

from pathlib import Path


def test_fraud_playbooks_migration_declares_snapshot_table() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "database/migrations/versions/0019_fraud_playbooks.py"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS fraud_playbook_snapshots" in migration
    assert "PRIMARY KEY (domain_name, playbook_id, version)" in migration
    assert "ALTER TABLE cases ADD COLUMN IF NOT EXISTS playbook_ref jsonb" in migration


def test_playbook_snapshot_kb_scope_migration_repairs_existing_table() -> None:
    migration = (
        Path("backend")
        / "database/migrations/versions/0020_playbook_snapshot_kb_scope.py"
    ).read_text(encoding="utf-8")

    assert "down_revision: str | None = \"0019_fraud_playbooks\"" in migration
    assert "ADD COLUMN IF NOT EXISTS knowledge_base_id text NOT NULL" in migration
    assert "DROP CONSTRAINT IF EXISTS pk_fraud_playbook_snapshots" in migration
    assert (
        "PRIMARY KEY (knowledge_base_id, domain_name, playbook_id, version)"
        in migration
    )
    assert (
        "knowledge_base_id, domain_name, status, updated_at DESC"
        in migration
    )
