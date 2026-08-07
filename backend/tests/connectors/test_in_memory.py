from __future__ import annotations

from datetime import datetime, timezone

from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorQuarantineRecordCreate,
    ConnectorSchedule,
    ConnectorSyncCounters,
    ConnectorSyncRunCreate,
    ConnectorSyncRunUpdate,
)
from connectors.adapters.in_memory import InMemoryConnectorRepository


def _definition_payload() -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id="cms-claims-drop",
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id="kb-cms",
        domain_name="medicare_fraud",
        credentials_ref="env:CMS_CONNECTOR_TOKEN",
        schedule=ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims-feed",
            mapping_version="v1",
            feed_name="claims_feed",
        ),
        config={"path": "/imports/cms/claims.csv"},
    )


def test_repository_saves_definitions_without_exposing_credentials() -> None:
    repository = InMemoryConnectorRepository()

    definition = repository.save_definition(_definition_payload())

    assert definition.connector_id == "cms-claims-drop"
    assert definition.credentials_ref == "env:CMS_CONNECTOR_TOKEN"
    assert definition.credentials_display == "env:CMS...OKEN"
    assert definition.config == {"path": "/imports/cms/claims.csv"}
    page = repository.list_definitions(knowledge_base_id="kb-cms")
    assert page.total_items == 1
    assert page.items[0].connector_id == "cms-claims-drop"


def test_repository_tracks_runs_and_quarantine_by_connector() -> None:
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition_payload())

    run = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
            idempotency_key="run-key-1",
        )
    )
    updated = repository.update_run(
        run.run_id,
        ConnectorSyncRunUpdate(
            status="completed",
            counters=ConnectorSyncCounters(
                pulled=12,
                accepted=10,
                quarantined=2,
                failed=0,
            ),
            ingest_correlation_id="ingest-1",
            source_cursor="cursor-12",
        ),
    )
    quarantine = repository.add_quarantine_record(
        ConnectorQuarantineRecordCreate(
            run_id=run.run_id,
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            source_record_id="claim-99",
            reason="missing provider_npi",
            raw_ref="object://connector/cms-claims-drop/claim-99.json",
        )
    )

    assert updated.status == "completed"
    assert updated.counters.quarantined == 2
    assert updated.completed_at is not None
    assert quarantine.quarantine_id.startswith(f"{run.run_id}:")
    assert repository.list_runs(connector_id="cms-claims-drop").total_items == 1
    assert repository.list_quarantine(run_id=run.run_id).items[0].source_record_id == "claim-99"


def test_get_run_returns_none_for_an_unknown_run() -> None:
    repository = InMemoryConnectorRepository()

    assert repository.get_run("no-such-run") is None


def test_get_run_returns_a_stored_run() -> None:
    repository = InMemoryConnectorRepository()
    created = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
        )
    )

    stored = repository.get_run(created.run_id)

    assert stored is not None
    assert stored.run_id == created.run_id
    assert stored.status == "queued"


def test_claim_sync_run_is_atomic() -> None:
    """Only one worker may take a queued run.

    Redis Streams is at-least-once and `reclaim_stale_pending` can hand the
    same event to a second worker, so the claim — not the handler — is what
    stops two workers pulling the same source concurrently.
    """
    repository = InMemoryConnectorRepository()
    created = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
        )
    )
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    first = repository.claim_sync_run(created.run_id, now=now)
    second = repository.claim_sync_run(created.run_id, now=now)

    assert first is not None
    assert first.status == "running"
    assert second is None


def test_claim_sync_run_returns_none_for_an_unknown_run() -> None:
    repository = InMemoryConnectorRepository()
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    assert repository.claim_sync_run("no-such-run", now=now) is None


def test_claim_sync_run_leaves_a_terminal_run_alone() -> None:
    """A completed run must not be dragged back to `running` by a redelivery."""
    repository = InMemoryConnectorRepository()
    created = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
        )
    )
    repository.update_run(created.run_id, ConnectorSyncRunUpdate(status="completed"))
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    assert repository.claim_sync_run(created.run_id, now=now) is None


def _stale_repository() -> tuple[InMemoryConnectorRepository, str, str]:
    """A repository with one fresh run and one aged run."""
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition_payload())
    fresh = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
        )
    )
    stale = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
        )
    )
    repository.update_run(stale.run_id, ConnectorSyncRunUpdate(status="running"))
    repository.set_updated_at_for_test(
        stale.run_id, datetime(2026, 8, 1, tzinfo=timezone.utc)
    )
    return repository, fresh.run_id, stale.run_id


def test_list_stale_runs_returns_only_old_non_terminal_runs() -> None:
    repository, fresh_id, stale_id = _stale_repository()

    found = repository.list_stale_runs(
        statuses=("queued", "running"),
        updated_before=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )

    assert [run.run_id for run in found] == [stale_id]
    assert fresh_id not in [run.run_id for run in found]


def test_list_stale_runs_never_returns_a_terminal_run() -> None:
    """Reaching a terminal state is what makes a run immune to the sweep."""
    repository, _, stale_id = _stale_repository()
    repository.update_run(stale_id, ConnectorSyncRunUpdate(status="completed"))
    repository.set_updated_at_for_test(
        stale_id, datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert (
        repository.list_stale_runs(
            statuses=("queued", "running"),
            updated_before=datetime(2026, 8, 5, tzinfo=timezone.utc),
        )
        == []
    )


def test_list_stale_runs_respects_its_limit() -> None:
    repository, _, _ = _stale_repository()

    found = repository.list_stale_runs(
        statuses=("queued", "running"),
        updated_before=datetime(2026, 8, 5, tzinfo=timezone.utc),
        limit=0,
    )

    assert found == []
