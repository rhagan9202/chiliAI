"""Integration tests for durable Postgres connector storage."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from connectors.adapters.postgres import PostgresConnectorRepository
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorQuarantineRecordCreate,
    ConnectorSchedule,
    ConnectorSyncCounters,
    ConnectorSyncRunCreate,
    ConnectorSyncRunUpdate,
)
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider

# parents: [0] connectors, [1] tests, [2] backend — the root alembic runs from.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_KB_ID = "kb-connectors-pg"
_CONNECTOR_ID = "cms-claims-drop-pg"
BASE_TIME = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping connector integration tests.")
    return url


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert connection_provider is not None
    _purge(connection_provider)
    yield connection_provider
    _purge(connection_provider)
    connection_provider.close()


def _purge(connection_provider: ConnectionProvider) -> None:
    with connection_provider.connection() as conn:
        # sync runs and quarantine rows cascade from connectors.
        conn.execute(
            "DELETE FROM connectors WHERE knowledge_base_id LIKE %s", (_KB_ID + "%",)
        )
        conn.execute(
            "DELETE FROM connector_sync_runs WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()


def _definition(
    *,
    credentials_ref: str | None = "env:CMS_CONNECTOR_TOKEN",
    schedule: ConnectorSchedule | None = None,
) -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id=_CONNECTOR_ID,
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
        credentials_ref=credentials_ref,
        schedule=schedule or ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims-feed",
            mapping_version="v1",
            feed_name="claims_feed",
        ),
        config={"path": "/imports/cms/claims.csv", "batch_size": 500},
    )


def _run_create(*, idempotency_key: str | None = None) -> ConnectorSyncRunCreate:
    return ConnectorSyncRunCreate(
        connector_id=_CONNECTOR_ID,
        knowledge_base_id=_KB_ID,
        requested_by="operator-1",
        idempotency_key=idempotency_key,
    )


def test_round_trips_a_definition(provider: ConnectionProvider) -> None:
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())

    stored = repository.get_definition(
        knowledge_base_id=_KB_ID, connector_id=_CONNECTOR_ID
    )

    assert stored is not None
    assert stored.name == "CMS Claims Drop"
    assert stored.source_type == "filesystem"
    assert stored.mapping.feed_name == "claims_feed"
    assert stored.config["path"] == "/imports/cms/claims.csv"
    assert stored.config["batch_size"] == 500


def test_definition_round_trip_preserves_every_field(
    provider: ConnectionProvider,
) -> None:
    """Guards the silent field loss the 0025 migration was corrected for.

    `domain_name` and the schedule *expression* are typed fields; a table that
    stored only `schedule_mode` would return a definition subtly different from
    the one that was saved.
    """
    repository = PostgresConnectorRepository(provider)
    saved = repository.save_definition(
        _definition(schedule=ConnectorSchedule(mode="cron", expression="0 3 * * *"))
    )

    stored = repository.get_definition(
        knowledge_base_id=_KB_ID, connector_id=_CONNECTOR_ID
    )

    assert stored is not None
    assert stored.domain_name == "medicare_fraud"
    assert stored.schedule.mode == "cron"
    assert stored.schedule.expression == "0 3 * * *"
    assert stored == saved


def test_stored_definition_never_exposes_the_credential(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresConnectorRepository(provider)
    stored = repository.save_definition(
        _definition(credentials_ref="env:CHILI_SFTP_PASSWORD")
    )

    # The ref names an env var; the value is never read, stored or returned.
    assert stored.credentials_display is not None
    assert "CHILI_SFTP_PASSWORD" not in stored.credentials_display


def test_claim_sync_run_is_atomic(provider: ConnectionProvider) -> None:
    """The conditional UPDATE is the concurrency guard.

    Two workers can be handed the same event by reclaim_stale_pending; only one
    may transition the run out of `queued`.
    """
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    run = repository.create_run(_run_create())

    first = repository.claim_sync_run(run.run_id, now=BASE_TIME)
    second = repository.claim_sync_run(run.run_id, now=BASE_TIME)

    assert first is not None
    assert first.status == "running"
    assert second is None


def test_claim_sync_run_returns_none_for_an_unknown_run(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresConnectorRepository(provider)

    assert repository.claim_sync_run("no-such-run", now=BASE_TIME) is None


def test_get_run_returns_none_for_an_unknown_run(provider: ConnectionProvider) -> None:
    repository = PostgresConnectorRepository(provider)

    assert repository.get_run("no-such-run") is None


def test_idempotency_key_is_enforced_by_the_database(
    provider: ConnectionProvider,
) -> None:
    """A partial unique index, not a service-side read-then-write."""
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    repository.create_run(_run_create(idempotency_key="sync:daily:2026-08-07"))

    with pytest.raises(ValueError, match="idempotency"):
        repository.create_run(_run_create(idempotency_key="sync:daily:2026-08-07"))


def test_two_runs_without_an_idempotency_key_both_insert(
    provider: ConnectionProvider,
) -> None:
    """The unique index is partial — NULL keys must not collide with each other."""
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())

    first = repository.create_run(_run_create())
    second = repository.create_run(_run_create())

    assert first.run_id != second.run_id


def test_update_run_persists_counters_and_cursor(provider: ConnectionProvider) -> None:
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    run = repository.create_run(_run_create())

    updated = repository.update_run(
        run.run_id,
        ConnectorSyncRunUpdate(
            status="running",
            counters=ConnectorSyncCounters(
                pulled=10, accepted=8, quarantined=2, failed=0
            ),
            source_cursor="offset:200",
            ingest_correlation_id="corr-1",
        ),
    )

    assert updated.counters.pulled == 10
    assert updated.counters.quarantined == 2
    assert updated.source_cursor == "offset:200"
    assert updated.ingest_correlation_id == "corr-1"

    reread = repository.get_run(run.run_id)
    assert reread is not None
    assert reread.counters.accepted == 8
    assert reread.source_cursor == "offset:200"


def test_terminal_update_stamps_completed_at(provider: ConnectionProvider) -> None:
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    run = repository.create_run(_run_create())

    completed = repository.update_run(
        run.run_id, ConnectorSyncRunUpdate(status="completed")
    )

    assert completed.status == "completed"
    assert completed.completed_at is not None


def test_quarantine_records_round_trip(provider: ConnectionProvider) -> None:
    """The quarantine table the plan's migration omitted entirely."""
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    run = repository.create_run(_run_create())

    repository.add_quarantine_record(
        ConnectorQuarantineRecordCreate(
            run_id=run.run_id,
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=_KB_ID,
            source_record_id="row-42",
            reason="missing required column: npi",
            raw_ref="s3://raw/row-42.json",
        )
    )

    page = repository.list_quarantine(run_id=run.run_id)

    assert page.total_items == 1
    assert page.items[0].source_record_id == "row-42"
    assert page.items[0].reason == "missing required column: npi"


def test_deleting_a_connector_cascades_to_runs_and_quarantine(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    run = repository.create_run(_run_create())
    repository.add_quarantine_record(
        ConnectorQuarantineRecordCreate(
            run_id=run.run_id,
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=_KB_ID,
            source_record_id="row-1",
            reason="bad row",
        )
    )

    _purge(provider)

    assert repository.get_run(run.run_id) is None
    assert repository.list_quarantine(run_id=run.run_id).total_items == 0


def test_list_runs_filters_by_connector(provider: ConnectionProvider) -> None:
    repository = PostgresConnectorRepository(provider)
    repository.save_definition(_definition())
    repository.create_run(_run_create())

    page = repository.list_runs(connector_id=_CONNECTOR_ID)
    other = repository.list_runs(connector_id="not-this-connector")

    assert page.total_items == 1
    assert other.total_items == 0


def test_the_same_connector_id_may_exist_in_two_knowledge_bases(
    provider: ConnectionProvider,
) -> None:
    """The repository protocol is KB-scoped, so storage must be too.

    A global primary key on `connector_id` makes the two backends disagree:
    the in-memory adapter keys on (kb, connector_id) and accepts this, while
    Postgres silently stores nothing and the definition reads back as missing.
    Found on the live stack, where registering the same connector into a second
    knowledge base returned 409.
    """
    repository = PostgresConnectorRepository(provider)
    other_kb = f"{_KB_ID}-second"
    repository.save_definition(_definition())
    second = _definition().model_copy(update={"knowledge_base_id": other_kb})

    repository.save_definition(second)

    first_stored = repository.get_definition(
        knowledge_base_id=_KB_ID, connector_id=_CONNECTOR_ID
    )
    second_stored = repository.get_definition(
        knowledge_base_id=other_kb, connector_id=_CONNECTOR_ID
    )
    assert first_stored is not None
    assert second_stored is not None
    assert first_stored.knowledge_base_id == _KB_ID
    assert second_stored.knowledge_base_id == other_kb


def test_deleting_one_knowledge_bases_connector_leaves_the_others(
    provider: ConnectionProvider,
) -> None:
    """The cascade must be scoped to the KB, not to the shared connector id."""
    repository = PostgresConnectorRepository(provider)
    other_kb = f"{_KB_ID}-second"
    repository.save_definition(_definition())
    repository.save_definition(
        _definition().model_copy(update={"knowledge_base_id": other_kb})
    )
    kept = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=other_kb,
            requested_by="operator-1",
        )
    )

    with provider.connection() as conn:
        conn.execute("DELETE FROM connectors WHERE knowledge_base_id = %s", (_KB_ID,))
        conn.commit()

    assert (
        repository.get_definition(
            knowledge_base_id=_KB_ID, connector_id=_CONNECTOR_ID
        )
        is None
    )
    assert repository.get_run(kept.run_id) is not None
