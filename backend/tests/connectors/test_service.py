from __future__ import annotations

import pytest

from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
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
