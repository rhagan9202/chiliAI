"""Tests for the explainability service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.exceptions import ExplainabilityConfigurationError
from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationSubgraph
from analytics.explainability.service import create_explainability_service
from analytics.explainability.service_models import ExplainabilityRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import ExplainabilityGeneratedEvent
from shared.types import Alert


def _alert() -> Alert:
    return Alert(
        id="alert-1",
        entity_type="provider",
        entity_id="provider-7",
        severity="high",
        title="Outlier",
        reasoning="Detected",
        created_at=datetime.now(timezone.utc),
    )


def test_explainability_service_generates_evidence_pack_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(
            contexts=[
                ExplanationContext(
                    knowledge_base_id="kb-1",
                    alert=_alert(),
                    explanation_items=[
                        ExplanationItem(
                            source_id="doc-1",
                            source_type="document",
                            quote="Claim volume spiked 4x.",
                            rationale="Claim frequency exceeded baseline.",
                            score=0.92,
                        ),
                        ExplanationItem(
                            source_id="edge-1",
                            source_type="graph_edge",
                            quote="Connected to flagged provider cluster.",
                            rationale="Shared referral path increased suspicion.",
                            score=0.88,
                        ),
                    ],
                    subgraph=ExplanationSubgraph(node_ids=["provider-7", "provider-9"], edge_ids=["edge-1"]),
                    confidence=0.91,
                    scores={"risk": 0.82, "timeseries": 0.9},
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1"))

    assert response.alert_id == "alert-1"
    assert len(response.evidence_items) == 2
    assert response.evidence_pack.alert_id == "alert-1"
    assert "Claim frequency exceeded baseline." in response.evidence_pack.reasoning
    assert isinstance(event_bus.published_events[-1], ExplainabilityGeneratedEvent)


def test_explainability_service_raises_for_unknown_alert() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(InMemoryExplainabilityContextSource(), event_bus=event_bus)

    with pytest.raises(ExplainabilityConfigurationError, match="No explainability context"):
        service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="missing-alert"))


def test_explainability_service_groups_narrative_by_source_type() -> None:
    event_bus = InMemoryEventBus()
    items = [
        ExplanationItem(
            source_id="doc-1",
            source_type="graph_neighbors",
            quote="Connected to flagged cluster.",
            rationale="Shared referral path increased suspicion.",
            score=0.95,
        ),
        ExplanationItem(
            source_id="doc-2",
            source_type="graph_neighbors",
            quote="Two-hop path to sanctioned entity.",
            rationale="Indirect link to sanctioned actor.",
            score=0.9,
        ),
        ExplanationItem(
            source_id="rf-1",
            source_type="risk_factors",
            quote="Risk score 0.92.",
            rationale="Composite risk above threshold.",
            score=0.85,
        ),
        ExplanationItem(
            source_id="an-1",
            source_type="anomalies",
            quote="Volume spike 4x.",
            rationale="Volume exceeded historical baseline.",
            score=0.8,
        ),
    ]
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(
            contexts=[
                ExplanationContext(
                    knowledge_base_id="kb-1",
                    alert=_alert(),
                    explanation_items=items,
                    subgraph=ExplanationSubgraph(node_ids=["provider-7"], edge_ids=[]),
                    confidence=0.9,
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.generate(
        ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1", max_evidence_items=4)
    )

    narrative = response.narrative
    headings = [section.heading for section in narrative.sections]
    assert headings == ["Graph Neighbors", "Risk Factors", "Anomalies"]

    graph_section = narrative.sections[0]
    assert graph_section.evidence_refs == ["doc-1", "doc-2"]
    assert "Shared referral path" in graph_section.body
    assert "Indirect link" in graph_section.body

    risk_section = narrative.sections[1]
    assert risk_section.evidence_refs == ["rf-1"]

    anomalies_section = narrative.sections[2]
    assert anomalies_section.evidence_refs == ["an-1"]

    assert response.evidence_pack.reasoning == narrative.summary
    for item in items:
        assert item.rationale in narrative.summary


def test_explainability_service_narrative_summary_matches_evidence_reasoning() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(
            contexts=[
                ExplanationContext(
                    knowledge_base_id="kb-1",
                    alert=_alert(),
                    explanation_items=[
                        ExplanationItem(
                            source_id="doc-1",
                            source_type="document",
                            quote="Q",
                            rationale="alpha",
                            score=0.5,
                        ),
                    ],
                    subgraph=ExplanationSubgraph(node_ids=["provider-7"], edge_ids=[]),
                    confidence=0.5,
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1"))

    assert response.narrative.summary == "alpha"
    assert response.evidence_pack.reasoning == "alpha"
    assert len(response.narrative.sections) == 1
    assert response.narrative.sections[0].heading == "Document"
    assert response.narrative.sections[0].evidence_refs == ["doc-1"]
