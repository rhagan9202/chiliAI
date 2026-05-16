"""Tests for Flow 3 — risk write-back."""

from __future__ import annotations

from agent.coordinator import handle_risk_scored_for_graph
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from events.adapters.in_memory import InMemoryEventBus
from events.types import RiskFactorReference, RiskScoredEvent, RiskScoredReference
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
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


def _event() -> RiskScoredEvent:
    return RiskScoredEvent(
        correlation_id="corr-risk",
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="req-1",
                entity_id="claim:c1",
                overall_score=0.82,
                risk_level="high",
                factor_count=1,
                factors=[
                    RiskFactorReference(
                        factor_name="anomaly",
                        raw_value=0.9,
                        weight=1.0,
                        contribution=0.82,
                    )
                ],
            )
        ],
    )


def test_flow3_persists_history_and_snapshots_graph() -> None:
    writer = InMemoryRiskHistoryWriter()
    service = _graph_service_with_entity()

    processed = handle_risk_scored_for_graph(
        _event(), risk_history_writer=writer, graph_service=service
    )

    assert processed == 1
    assert (
        writer.load_historical_score(knowledge_base_id="kb-1", entity_id="claim:c1")
        == 0.82
    )
    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["risk_score"] == 0.82
    assert entity.properties["risk_level"] == "high"
    assert "risk_assessed_at" in entity.properties


def test_flow3_is_idempotent_on_replay() -> None:
    writer = InMemoryRiskHistoryWriter()
    service = _graph_service_with_entity()
    event = _event()

    processed_1 = handle_risk_scored_for_graph(
        event, risk_history_writer=writer, graph_service=service
    )
    processed_2 = handle_risk_scored_for_graph(
        event, risk_history_writer=writer, graph_service=service
    )

    assert processed_1 == 1
    assert processed_2 == 1

    assert (
        writer.load_historical_score(knowledge_base_id="kb-1", entity_id="claim:c1")
        == 0.82
    )

    entity = service.get_entity("kb-1", "claim:c1")
    assert entity is not None
    assert entity.properties["risk_score"] == 0.82
    assert entity.properties["risk_level"] == "high"
