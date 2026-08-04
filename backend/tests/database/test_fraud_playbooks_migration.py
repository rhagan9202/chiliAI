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
