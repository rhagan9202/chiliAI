"""Tests for real evidence-pack extraction + persistence in Flow B (BL-005)."""

from __future__ import annotations

from agent.coordinator import _build_explanation_context, _run_explainability_stage
from analytics.explainability.adapters.evidence_in_memory import (
    InMemoryEvidencePackRepository,
)
from analytics.explainability.adapters.in_memory import (
    InMemoryExplainabilityContextSource,
)
from analytics.explainability.service import create_explainability_service
from analytics.risk.service_models import RiskAssessmentResponse, RiskFactorScore
from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedEvent
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


def _risk_response() -> RiskAssessmentResponse:
    return RiskAssessmentResponse(
        request_id="req-1",
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        overall_score=0.82,
        risk_level="high",
        factor_count=1,
        factors=[
            RiskFactorScore(
                factor_name="upcoding",
                raw_value=0.9,
                weight=1.0,
                contribution=0.7,
                rationale="Unusual cardiac billing volume.",
            )
        ],
    )


def test_build_explanation_context_uses_graph_subgraph_and_risk_scores() -> None:
    context = _build_explanation_context(
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        alert_id="alert-provider-1-req-1",
        risk_response=_risk_response(),
    )

    # Subgraph node ids come from graph.get_subgraph, not seeded constants.
    assert set(context.subgraph.node_ids) >= {"provider-1", "claim-1", "beneficiary-1"}
    assert "upcoding" in context.scores
    assert context.scores["overall"] == 0.82
    assert context.confidence == 0.82
    assert any(item.quote == "upcoding" for item in context.explanation_items)


def test_run_explainability_stage_persists_real_pack() -> None:
    repository = InMemoryEvidencePackRepository()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(), event_bus=InMemoryEventBus()
    )

    reference = _run_explainability_stage(
        event=GraphUpdatedEvent(correlation_id="corr-1", documents=[]),
        explainability_service=service,
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        risk_response=_risk_response(),
        event_bus=InMemoryEventBus(),
        evidence_pack_repository=repository,
    )

    assert reference is not None
    persisted = repository.get("kb-1", reference.evidence_pack_id)
    assert persisted is not None
    assert set(persisted.subgraph_nodes) >= {"provider-1", "claim-1", "beneficiary-1"}
    assert persisted.scores["overall"] == 0.82


def test_run_explainability_stage_without_repository_still_returns_reference() -> None:
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(), event_bus=InMemoryEventBus()
    )

    reference = _run_explainability_stage(
        event=GraphUpdatedEvent(correlation_id="corr-1", documents=[]),
        explainability_service=service,
        graph_service=_graph_service(),
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        risk_response=_risk_response(),
        event_bus=InMemoryEventBus(),
        evidence_pack_repository=None,
    )

    assert reference is not None
    assert reference.evidence_pack_id
