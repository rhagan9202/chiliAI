"""Migration shape tests for durable score-run persistence."""

from __future__ import annotations

from pathlib import Path


def _migration(name: str) -> str:
    # Resolve from this file, never the cwd: `make test` and CI both run with
    # `backend/` as the working directory, so a cwd-relative path here resolves
    # to `backend/backend/...` and the test never executes.
    return (
        Path(__file__).resolve().parents[2] / "database/migrations/versions" / name
    ).read_text(encoding="utf-8")


def test_score_runs_migration_declares_the_run_table() -> None:
    migration = _migration("0024_score_runs.py")

    assert 'revision: str = "0024_score_runs"' in migration
    assert 'down_revision: str | None = "0023_eval_dataset_refs"' in migration
    assert "CREATE TABLE IF NOT EXISTS score_runs" in migration
    assert "id text PRIMARY KEY" in migration
    assert "entity_cursor text" in migration
    assert "ix_score_runs_kb_status" in migration


def test_score_runs_migration_enforces_idempotency_in_the_database() -> None:
    """A partial unique index, not a read-then-write race in the service."""
    migration = _migration("0024_score_runs.py")

    assert "ux_score_runs_kb_idempotency" in migration
    assert "WHERE idempotency_key IS NOT NULL" in migration


def test_score_runs_migration_declares_the_batch_table() -> None:
    migration = _migration("0024_score_runs.py")

    assert "CREATE TABLE IF NOT EXISTS score_batches" in migration
    assert "run_id text NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE" in migration
    assert "UNIQUE (run_id, batch_number)" in migration
    assert "ix_score_batches_run_status" in migration


def test_score_runs_migration_downgrade_drops_both_tables() -> None:
    migration = _migration("0024_score_runs.py")

    assert "DROP TABLE IF EXISTS score_batches" in migration
    assert "DROP TABLE IF EXISTS score_runs" in migration
