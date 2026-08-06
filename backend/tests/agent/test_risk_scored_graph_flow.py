"""Tests for Flow 3 — risk write-back."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent.coordinator import handle_event, handle_risk_scored_for_graph
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from analytics.risk.projection_service import RiskProjectionService
from analytics.risk.projections import (
    InMemoryRiskProjectionRepository,
    RiskProjectionQuery,
)
from config.loader import load_config
from events.adapters.in_memory import InMemoryEventBus
from events.protocols import EventDelivery
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


def _event(*, occurred_at: datetime | None = None) -> RiskScoredEvent:
    return RiskScoredEvent(
        correlation_id="corr-risk",
        occurred_at=occurred_at or datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
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
                        factor_name="claim_amount_threshold_exposure",
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
    entity = service.get_entity(["kb-1"], "claim:c1")
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

    entity = service.get_entity(["kb-1"], "claim:c1")
    assert entity is not None
    assert entity.properties["risk_score"] == 0.82
    assert entity.properties["risk_level"] == "high"


def test_risk_scored_event_projects_live_risk_read_model() -> None:
    writer = InMemoryRiskHistoryWriter()
    graph_service = _graph_service_with_entity()
    projection_repository = InMemoryRiskProjectionRepository()
    projection_service = RiskProjectionService(projection_repository)
    object_store = InMemoryObjectStore()

    handle_event(
        EventDelivery(event=_event(), stream="risk.scored", event_id="1-0"),
        None,  # type: ignore[arg-type]
        document_chunker=None,  # type: ignore[arg-type]
        document_extractor=None,  # type: ignore[arg-type]
        extraction_validator=None,  # type: ignore[arg-type]
        graph_service=graph_service,
        object_store=object_store,
        event_bus=InMemoryEventBus(),
        risk_history_writer=writer,
        risk_projection_service=projection_service,
        domain_config=load_config(
            Path(__file__).resolve().parents[2] / "config/defaults/medicare_fraud.yaml"
        ),
    )

    rows = projection_repository.list(
        RiskProjectionQuery(knowledge_base_id="kb-1")
    ).items
    assert len(rows) == 1
    assert rows[0].entity_id == "claim:c1"
    assert rows[0].entity_type == "claim"
    assert rows[0].overall_score == 0.82
    assert rows[0].risk_level == "high"
    assert rows[0].score_run_id == "req-1"
    assert rows[0].model_version == "risk-score-history"
    assert rows[0].catalog_version == "risk-score-history"
    assert rows[0].top_typology_ids == ["policy_threshold_exposure"]
    assert rows[0].scored_at == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_risk_scored_replay_does_not_refresh_projection() -> None:
    writer = InMemoryRiskHistoryWriter()
    graph_service = _graph_service_with_entity()
    projection_repository = InMemoryRiskProjectionRepository()
    projection_service = RiskProjectionService(projection_repository)
    event = _event(occurred_at=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc))

    handle_risk_scored_for_graph(
        event,
        risk_history_writer=writer,
        graph_service=graph_service,
        risk_projection_service=projection_service,
        feature_typology_index={"claim_amount_threshold_exposure": ["policy_threshold_exposure"]},
    )
    first = projection_repository.get("kb-1", "claim:c1")
    replay = event.model_copy(
        update={"occurred_at": datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)}
    )
    handle_risk_scored_for_graph(
        replay,
        risk_history_writer=writer,
        graph_service=graph_service,
        risk_projection_service=projection_service,
        feature_typology_index={"claim_amount_threshold_exposure": ["policy_threshold_exposure"]},
    )

    assert first is not None
    assert projection_repository.get("kb-1", "claim:c1") == first
