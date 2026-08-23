"""Tests for real evidence-pack context extraction in Flow B (BL-005).

The persistence + alert-reference wiring of ``_run_explainability_stage`` is
exercised end-to-end by the Flow B coordinator tests; here we cover the public
``build_explanation_context`` unit that derives a real explanation context from
``graph.get_subgraph`` plus the risk assessment (replacing the seeded context).
"""

from __future__ import annotations

from agent.coordinator import build_explanation_context
from analytics.risk.service_models import RiskAssessmentResponse, RiskFactorScore
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService, create_graph_service
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def _graph_service() -> GraphService:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="provider-1", type="provider", properties={}),
            Entity(id="claim-1", type="claim", properties={}),
            Entity(id="beneficiary-1", type="beneficiary", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(id="rel-1", type="submitted_by", source_id="claim-1", target_id="provider-1"),
            Relationship(id="rel-2", type="billed_for", source_id="claim-1", target_id="beneficiary-1"),
        ],
    )
    return create_graph_service(
        repository, object_store=InMemoryObjectStore(), event_bus=InMemoryEventBus()
    )


def _risk_response(*, factors: list[RiskFactorScore] | None = None) -> RiskAssessmentResponse:
    resolved = (
        factors
        if factors is not None
        else [
            RiskFactorScore(
                factor_name="upcoding",
                raw_value=0.9,
                weight=1.0,
                contribution=0.7,
                rationale="Unusual cardiac billing volume.",
            )
        ]
    )
    return RiskAssessmentResponse(
        request_id="req-1",
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        overall_score=0.82,
        risk_level="high",
        factor_count=len(resolved),
        factors=resolved,
    )


def test_build_explanation_context_uses_graph_subgraph_and_risk_scores() -> None:
    context = build_explanation_context(
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        alert_id="alert-provider-1-req-1",
        risk_response=_risk_response(),
        correlation_id="corr-1",
    )

    # Subgraph node ids come from graph.get_subgraph, not seeded constants.
    assert set(context.subgraph.node_ids) >= {"provider-1", "claim-1", "beneficiary-1"}
    assert "upcoding" in context.scores
    assert context.scores["overall"] == 0.82
    assert context.confidence == 0.82
    assert any(item.quote == "upcoding" for item in context.explanation_items)
    assert context.alert.id == "alert-provider-1-req-1"
    assert context.alert.entity_type == "provider"
    assert context.lineage.score_request_id == "req-1"
    assert context.lineage.correlation_id == "corr-1"


def test_build_explanation_context_preserves_signal_floor_metadata() -> None:
    response = _risk_response().model_copy(
        update={"signal_count": 1, "min_risk_signals": 1}
    )

    context = build_explanation_context(
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        alert_id="alert-provider-1-req-1",
        risk_response=response,
        correlation_id="corr-1",
    )

    assert context.scores["signal_count"] == 1.0
    assert context.scores["min_risk_signals"] == 1.0


def test_build_explanation_context_falls_back_to_seed_when_no_factors() -> None:
    context = build_explanation_context(
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        alert_id="alert-provider-1-req-2",
        risk_response=_risk_response(factors=[]),
    )

    # No risk factors -> a single risk-summary item keeps the context valid.
    assert len(context.explanation_items) == 1
    assert context.explanation_items[0].source_type == "risk_summary"
    assert context.scores["overall"] == 0.82


def test_build_explanation_context_handles_entity_absent_from_graph() -> None:
    # An entity with no graph node still yields a valid single-node subgraph.
    context = build_explanation_context(
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="ghost-entity",
        alert_id="alert-ghost-req-3",
        risk_response=_risk_response(),
    )

    assert context.subgraph.node_ids == ["ghost-entity"]
    assert context.alert.entity_type == "entity"
