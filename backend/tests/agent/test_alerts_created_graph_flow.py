"""Tests for Flow 4 — alert write-back."""

from __future__ import annotations

from agent.coordinator import handle_alerts_created_for_graph
from events.adapters.in_memory import InMemoryEventBus
from events.types import AlertCreatedReference, AlertsCreatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore


def _graph_service_with_entity() -> GraphService:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    service.upsert_records_graph(
        "kb-1", [Entity(id="claim:c1", type="claim", properties={})], []
    )
    return service


def _reference(alert_id: str) -> AlertCreatedReference:
    return AlertCreatedReference(
        knowledge_base_id="kb-1",
        alert_id=alert_id,
        entity_id="claim:c1",
        severity="high",
        entity_type="claim",
        status="open",
        title="Anomalous claim",
        reasoning="score exceeded threshold",
        metric_name="claim_anomaly",
    )


def _event() -> AlertsCreatedEvent:
    return AlertsCreatedEvent(
        correlation_id="corr-alert",
        alerts=[_reference("a-1"), _reference("a-2")],
    )


def test_flow4_persists_history_and_snapshots_graph() -> None:
    writer = InMemoryAlertHistoryWriter()
    service = _graph_service_with_entity()

    processed = handle_alerts_created_for_graph(
        _event(), alert_history_writer=writer, graph_service=service
    )

    assert processed == 2
    assert (
        writer.count_open_alerts(knowledge_base_id="kb-1", entity_id="claim:c1") == 2
    )
    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["active_alert_count"] == 2
    assert entity.properties["last_alert_severity"] == "high"
    assert "last_alert_at" in entity.properties


def test_flow4_is_idempotent_on_replay() -> None:
    writer = InMemoryAlertHistoryWriter()
    service = _graph_service_with_entity()
    event = _event()

    handle_alerts_created_for_graph(
        event, alert_history_writer=writer, graph_service=service
    )
    handle_alerts_created_for_graph(
        event, alert_history_writer=writer, graph_service=service
    )
    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["active_alert_count"] == 2
