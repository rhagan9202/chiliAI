"""Capability adapter for connector sync status."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from capabilities.models import CapabilityExecutionEnvelope, JsonValue
from capabilities.service import CapabilityRegistryService
from connectors.models import ConnectorDefinition, ConnectorSyncRun
from connectors.service import ConnectorService

CONNECTOR_SYNC_STATUS_CAPABILITY_ID = "connector.sync.status"


def execute_connector_sync_status_capability(
    *,
    connector_service: ConnectorService,
    capability_registry: CapabilityRegistryService,
    actor_roles: Sequence[str],
    knowledge_base_id: str,
    connector_id: str,
    # Required, not defaulted: an adapter that lets its caller omit the
    # authorization context reintroduces the fail-open branch one layer up.
    domain_name: str | None,
    environment_tag: str | None,
) -> CapabilityExecutionEnvelope:
    """Authorize and execute the `connector.sync.status` capability."""

    authorized = capability_registry.authorize(
        CONNECTOR_SYNC_STATUS_CAPABILITY_ID,
        actor_roles=actor_roles,
        domain_name=domain_name,
        environment_tag=environment_tag,
    )
    if not authorized.success:
        return authorized

    connector = _find_connector(
        connector_service=connector_service,
        knowledge_base_id=knowledge_base_id,
        connector_id=connector_id,
    )
    if connector is None:
        return capability_registry.execution_failure(
            CONNECTOR_SYNC_STATUS_CAPABILITY_ID,
            error_code="connector_not_found",
            error_message=(
                f"Connector '{connector_id}' was not found in knowledge base "
                f"'{knowledge_base_id}'."
            ),
        )

    latest_run = _latest_run(
        connector_service=connector_service,
        knowledge_base_id=knowledge_base_id,
        connector_id=connector_id,
    )
    return capability_registry.execution_success(
        CONNECTOR_SYNC_STATUS_CAPABILITY_ID,
        output=_status_output(connector, latest_run),
    )


def _find_connector(
    *,
    connector_service: ConnectorService,
    knowledge_base_id: str,
    connector_id: str,
) -> ConnectorDefinition | None:
    connectors = connector_service.list_connectors(
        knowledge_base_id=knowledge_base_id,
        limit=500,
    )
    for connector in connectors.items:
        if connector.connector_id == connector_id:
            return connector
    return None


def _latest_run(
    *,
    connector_service: ConnectorService,
    knowledge_base_id: str,
    connector_id: str,
) -> ConnectorSyncRun | None:
    runs = connector_service.list_runs(
        knowledge_base_id=knowledge_base_id,
        connector_id=connector_id,
        limit=1,
    )
    return runs.items[0] if runs.items else None


def _status_output(
    connector: ConnectorDefinition,
    latest_run: ConnectorSyncRun | None,
) -> dict[str, JsonValue]:
    if latest_run is None:
        return {
            "connector_id": connector.connector_id,
            "knowledge_base_id": connector.knowledge_base_id,
            "connector_name": connector.name,
            "source_type": connector.source_type,
            "connector_status": connector.status,
            "sync_status": "never_synced",
            "run_id": None,
            "last_synced_at": None,
            "started_at": None,
            "updated_at": None,
            "counters": {
                "pulled": 0,
                "accepted": 0,
                "quarantined": 0,
                "failed": 0,
            },
            "source_cursor": None,
            "ingest_correlation_id": None,
            "error_message": None,
        }

    return {
        "connector_id": connector.connector_id,
        "knowledge_base_id": connector.knowledge_base_id,
        "connector_name": connector.name,
        "source_type": connector.source_type,
        "connector_status": connector.status,
        "sync_status": latest_run.status,
        "run_id": latest_run.run_id,
        "last_synced_at": _isoformat(latest_run.completed_at),
        "started_at": _isoformat(latest_run.started_at),
        "updated_at": _isoformat(latest_run.updated_at),
        "counters": latest_run.counters.model_dump(mode="json"),
        "source_cursor": latest_run.source_cursor,
        "ingest_correlation_id": latest_run.ingest_correlation_id,
        "error_message": latest_run.error_message,
    }


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


__all__ = [
    "CONNECTOR_SYNC_STATUS_CAPABILITY_ID",
    "execute_connector_sync_status_capability",
]
