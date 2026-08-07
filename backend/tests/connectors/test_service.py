from __future__ import annotations

import pytest

from connectors.exceptions import ConnectorValidationError
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorScheduleMode,
    ConnectorSourceType,
    ConnectorSyncCounters,
)
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.service import ConnectorService


def _payload(
    *,
    connector_id: str = "cms-claims-drop",
    knowledge_base_id: str = "kb-cms",
    path: str = "/imports/cms/claims.csv",
) -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id=connector_id,
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id=knowledge_base_id,
        domain_name="medicare_fraud",
        credentials_ref="env:CMS_CONNECTOR_TOKEN",
        schedule=ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims-feed",
            mapping_version="v1",
            feed_name="claims_feed",
        ),
        config={"path": path},
    )


def test_register_connector_rejects_cross_kb_payload() -> None:
    service = ConnectorService(InMemoryConnectorRepository())

    with pytest.raises(ValueError, match="knowledge_base_id mismatch"):
        service.register_connector("kb-other", _payload(knowledge_base_id="kb-cms"))


def test_register_connector_is_idempotent_only_for_matching_definition() -> None:
    service = ConnectorService(InMemoryConnectorRepository())

    first = service.register_connector("kb-cms", _payload())
    second = service.register_connector("kb-cms", _payload())

    assert second == first
    with pytest.raises(ValueError, match="already exists with a different definition"):
        service.register_connector("kb-cms", _payload(path="/imports/cms/other.csv"))


def test_start_sync_reuses_run_for_same_idempotency_key() -> None:
    service = ConnectorService(InMemoryConnectorRepository())
    service.register_connector("kb-cms", _payload())

    first = service.start_sync(
        knowledge_base_id="kb-cms",
        connector_id="cms-claims-drop",
        requested_by="operator-1",
        idempotency_key="run-key-1",
    )
    second = service.start_sync(
        knowledge_base_id="kb-cms",
        connector_id="cms-claims-drop",
        requested_by="operator-1",
        idempotency_key="run-key-1",
    )

    assert second.run_id == first.run_id
    assert service.list_runs(connector_id="cms-claims-drop").total_items == 1


def test_complete_fail_and_quarantine_lifecycle() -> None:
    service = ConnectorService(InMemoryConnectorRepository())
    service.register_connector("kb-cms", _payload())

    run = service.start_sync(
        knowledge_base_id="kb-cms",
        connector_id="cms-claims-drop",
        requested_by="operator-1",
    )
    completed = service.complete_sync(
        run.run_id,
        counters=ConnectorSyncCounters(pulled=5, accepted=4, quarantined=1),
        ingest_correlation_id="ingest-1",
        source_cursor="cursor-5",
    )
    quarantine = service.quarantine_record(
        run_id=run.run_id,
        connector_id="cms-claims-drop",
        knowledge_base_id="kb-cms",
        source_record_id="claim-5",
        reason="missing provider_npi",
        raw_ref="object://connector/cms-claims-drop/claim-5.json",
    )
    failed = service.fail_sync(run.run_id, error_message="downstream unavailable")

    assert completed.status == "completed"
    assert completed.ingest_correlation_id == "ingest-1"
    assert completed.source_cursor == "cursor-5"
    assert quarantine.source_record_id == "claim-5"
    assert failed.status == "failed"
    assert failed.error_message == "downstream unavailable"


def _unimplemented_payload(
    *,
    source_type: ConnectorSourceType = "filesystem",
    schedule: ConnectorSchedule | None = None,
) -> ConnectorDefinitionCreate:
    payload = _payload()
    return payload.model_copy(
        update={
            "source_type": source_type,
            "schedule": schedule or payload.schedule,
        }
    )


@pytest.mark.parametrize("source_type", ["object_store", "http"])
def test_registering_an_unimplemented_source_type_is_rejected(
    source_type: ConnectorSourceType,
) -> None:
    """A Literal that accepts values nothing honours is the defect being removed.

    Both types are in `ConnectorSourceType` because they are planned, and
    accepting one would queue a sync run that no adapter can ever serve.
    """
    service = ConnectorService(InMemoryConnectorRepository())

    with pytest.raises(ConnectorValidationError, match="not implemented"):
        service.register_connector(
            "kb-cms", _unimplemented_payload(source_type=source_type)
        )


@pytest.mark.parametrize("mode", ["interval", "cron"])
def test_registering_a_scheduled_mode_is_rejected(mode: ConnectorScheduleMode) -> None:
    """Nothing schedules connectors yet, so a schedule would never fire."""
    service = ConnectorService(InMemoryConnectorRepository())

    with pytest.raises(ConnectorValidationError, match="not implemented"):
        service.register_connector(
            "kb-cms",
            _unimplemented_payload(
                schedule=ConnectorSchedule(mode=mode, expression="0 3 * * *")
            ),
        )


def test_the_rejection_names_what_is_implemented() -> None:
    """An operator needs to know what to use, not only what failed."""
    service = ConnectorService(InMemoryConnectorRepository())

    with pytest.raises(ConnectorValidationError) as excinfo:
        service.register_connector("kb-cms", _unimplemented_payload(source_type="http"))

    assert "filesystem" in str(excinfo.value)


def test_a_validation_error_is_not_a_value_error() -> None:
    """`register_connector` already raises ValueError for conflicts -> HTTP 409.

    If this were a ValueError subclass an unimplemented source type would be
    reported as a conflict rather than as invalid input.
    """
    assert not issubclass(ConnectorValidationError, ValueError)


def test_the_implemented_source_set_matches_the_adapters_the_worker_builds() -> None:
    """The guard and the worker's adapter map must not drift apart.

    A source type accepted here but absent from the worker's adapters registers
    fine and then fails every run; one present there but rejected here is
    unreachable.
    """
    from agent.coordinator import build_connector_source_adapters
    from connectors.service import IMPLEMENTED_SOURCE_TYPES

    assert set(build_connector_source_adapters()) == set(IMPLEMENTED_SOURCE_TYPES)


def test_starting_a_sync_for_an_unimplemented_source_is_rejected() -> None:
    """Defence in depth for connectors stored before the guard existed.

    Without this the run is created, queued, and only fails once a worker picks
    it up — the operator sees a failed run instead of a straight answer.
    """
    repository = InMemoryConnectorRepository()
    # Written straight to the repository: the service would refuse it now.
    repository.save_definition(_unimplemented_payload(source_type="http"))
    service = ConnectorService(repository)

    with pytest.raises(ConnectorValidationError, match="not implemented"):
        service.start_sync(
            knowledge_base_id="kb-cms",
            connector_id="cms-claims-drop",
            requested_by="operator-1",
        )


def test_starting_a_sync_for_an_implemented_source_still_works() -> None:
    repository = InMemoryConnectorRepository()
    service = ConnectorService(repository)
    service.register_connector("kb-cms", _payload())

    run = service.start_sync(
        knowledge_base_id="kb-cms",
        connector_id="cms-claims-drop",
        requested_by="operator-1",
    )

    assert run.status == "queued"
