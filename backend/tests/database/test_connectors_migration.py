"""Migration shape tests for durable connector persistence."""

from __future__ import annotations

from pathlib import Path


def _migration(name: str) -> str:
    # Resolve from this file, never the cwd: `make test` and CI both run with
    # `backend/` as the working directory, so a cwd-relative path here resolves
    # to `backend/backend/...` and the test never executes.
    return (
        Path(__file__).resolve().parents[2] / "database/migrations/versions" / name
    ).read_text(encoding="utf-8")


def test_connectors_migration_declares_the_definition_table() -> None:
    migration = _migration("0025_connectors.py")

    assert 'revision: str = "0025_connectors"' in migration
    assert 'down_revision: str | None = "0024_score_runs"' in migration
    assert "CREATE TABLE IF NOT EXISTS connectors" in migration
    assert "ix_connectors_kb" in migration


def test_connectors_are_keyed_by_knowledge_base_and_connector_id() -> None:
    """KB-scoped storage, matching the KB-scoped repository protocol.

    `get_definition(*, knowledge_base_id, connector_id)` and the in-memory
    adapter both key on the pair. A global primary key on `connector_id` alone
    lets the two backends disagree — the same connector id in a second
    knowledge base works in memory and silently stores nothing in Postgres.
    """
    migration = _migration("0025_connectors.py")

    assert (
        "CONSTRAINT pk_connectors PRIMARY KEY (knowledge_base_id, connector_id)"
        in migration
    )
    # The sync-run foreign key has to follow the composite key.
    assert "FOREIGN KEY (knowledge_base_id, connector_id)" in migration


def test_connectors_migration_declares_the_sync_run_table() -> None:
    migration = _migration("0025_connectors.py")

    assert "CREATE TABLE IF NOT EXISTS connector_sync_runs" in migration
    assert "source_cursor text" in migration
    assert "ix_connector_sync_runs_connector_status" in migration


def test_sync_run_idempotency_is_enforced_in_the_database() -> None:
    """A partial unique index, not a read-then-write race in the service.

    Two concurrent sync requests carrying the same key must not both insert;
    the index is what makes the second one fail rather than duplicate a run.
    """
    migration = _migration("0025_connectors.py")

    assert "ux_connector_sync_runs_idempotency" in migration
    # KB-scoped, matching the service lookup: two knowledge bases sharing a
    # connector id must not share one idempotency namespace.
    assert "(knowledge_base_id, connector_id, idempotency_key)" in migration
    assert "WHERE idempotency_key IS NOT NULL" in migration


def test_connector_columns_cover_every_stored_definition_field() -> None:
    """Guards silent field loss on the jsonb/column round trip.

    `domain_name` and the schedule *expression* are real fields on
    ``ConnectorDefinition``; a table that stores only ``schedule_mode`` drops
    the expression, and a definition that round-trips through Postgres would
    come back subtly different from the one that was saved.
    """
    migration = _migration("0025_connectors.py")

    assert "domain_name text" in migration
    assert "schedule_mode text" in migration
    assert "schedule_expression text" in migration


def test_connectors_table_has_no_column_the_model_cannot_supply() -> None:
    """`ConnectorDefinition` has no `created_by`.

    A NOT NULL column with no model field behind it can only be satisfied by
    inventing a value at the adapter, which is how a schema starts lying about
    provenance.
    """
    migration = _migration("0025_connectors.py")

    assert "created_by" not in migration


def test_migration_declares_the_quarantine_table() -> None:
    """`GET /connectors/{id}/quarantine` is a live route.

    The repository protocol has `add_quarantine_record`/`list_quarantine`, and
    the executor quarantines invalid rows rather than dropping them. Without a
    table, a Postgres-backed repository would either error or silently report
    an empty quarantine while the run counters claim rows were quarantined.
    """
    migration = _migration("0025_connectors.py")

    assert "CREATE TABLE IF NOT EXISTS connector_quarantine_records" in migration
    assert "quarantine_id text PRIMARY KEY" in migration
    assert "source_record_id text NOT NULL" in migration
    assert "ix_connector_quarantine_run" in migration


def test_downgrade_drops_everything_the_upgrade_created() -> None:
    """Replay is a CI gate: upgrade -> downgrade -> upgrade must be clean."""
    migration = _migration("0025_connectors.py")
    downgrade = migration.split("def downgrade()")[1]

    for table in (
        "connector_quarantine_records",
        "connector_sync_runs",
        "connectors",
    ):
        assert f"DROP TABLE IF EXISTS {table}" in downgrade
