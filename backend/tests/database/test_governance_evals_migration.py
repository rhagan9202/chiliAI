from __future__ import annotations

from pathlib import Path


def test_governance_evals_migration_declares_eval_runs_table() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "database/migrations/versions/0022_governance_eval_runs.py"
    ).read_text(encoding="utf-8")

    assert "revision: str = \"0022_governance_eval_runs\"" in migration
    assert "down_revision: str | None = \"0021_workflow_definitions\"" in migration
    assert "CREATE TABLE IF NOT EXISTS governance_eval_runs" in migration
    assert "run_id text PRIMARY KEY" in migration
    assert "metrics jsonb NOT NULL" in migration
    assert "drift_summary jsonb NOT NULL" in migration
    assert "dataset_source_refs jsonb NOT NULL" in migration
    assert "ADD COLUMN IF NOT EXISTS dataset_source_refs" in migration
    assert "approval jsonb" in migration
    assert "knowledge_base_id, status, created_at DESC" in migration


def test_governance_eval_dataset_source_refs_migration_is_additive() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "database/migrations/versions/0023_governance_eval_dataset_source_refs.py"
    ).read_text(encoding="utf-8")

    assert "revision: str = \"0023_eval_dataset_refs\"" in migration
    assert "down_revision: str | None = \"0022_governance_eval_runs\"" in migration
    assert "ADD COLUMN IF NOT EXISTS dataset_source_refs" in migration
    assert "DROP COLUMN IF EXISTS dataset_source_refs" in migration
