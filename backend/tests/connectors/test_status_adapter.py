from __future__ import annotations

from capabilities.service import create_default_capability_registry_service
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncCounters,
)
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.service import ConnectorService
from connectors.status_adapter import execute_connector_sync_status_capability


def _connector_payload() -> ConnectorDefinitionCreate:
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


def test_status_capability_returns_latest_run_without_raw_credentials() -> None:
    service = ConnectorService(InMemoryConnectorRepository())
    registry = create_default_capability_registry_service()
    service.register_connector("kb-cms", _connector_payload())
    run = service.start_sync(
        knowledge_base_id="kb-cms",
        connector_id="cms-claims-drop",
        requested_by="analyst-1",
        idempotency_key="sync-1",
    )
    service.complete_sync(
        run.run_id,
        counters=ConnectorSyncCounters(
            pulled=12,
            accepted=10,
            quarantined=1,
            failed=1,
        ),
        ingest_correlation_id="ingest-123",
        source_cursor="claims.csv:12",
    )

    envelope = execute_connector_sync_status_capability(
        connector_service=service,
        capability_registry=registry,
        actor_roles=["viewer"],
        knowledge_base_id="kb-cms",
        connector_id="cms-claims-drop",
        domain_name="medicare_fraud",
        environment_tag="production",
    )

    assert envelope.success is True
    assert envelope.capability_id == "connector.sync.status"
    assert envelope.audit_required is False
    assert envelope.output is not None
    assert envelope.output["connector_id"] == "cms-claims-drop"
    assert envelope.output["connector_name"] == "CMS Claims Drop"
    assert envelope.output["source_type"] == "filesystem"
    assert envelope.output["connector_status"] == "active"
    assert envelope.output["sync_status"] == "completed"
    assert envelope.output["counters"] == {
        "pulled": 12,
        "accepted": 10,
        "quarantined": 1,
        "failed": 1,
    }
    assert envelope.output["source_cursor"] == "claims.csv:12"
    assert envelope.output["ingest_correlation_id"] == "ingest-123"
    assert "credentials_ref" not in envelope.output


def test_status_capability_returns_not_found_for_unknown_connector() -> None:
    service = ConnectorService(InMemoryConnectorRepository())
    registry = create_default_capability_registry_service()

    envelope = execute_connector_sync_status_capability(
        connector_service=service,
        capability_registry=registry,
        actor_roles=["viewer"],
        knowledge_base_id="kb-cms",
        connector_id="missing",
        domain_name="medicare_fraud",
        environment_tag="production",
    )

    assert envelope.success is False
    assert envelope.error_code == "connector_not_found"
