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


def test_explainability_service_generates_evidence_pack_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(
            contexts=[
                ExplanationContext(
                    knowledge_base_id="kb-1",
                    alert=Alert(
                        id="alert-1",
                        entity_type="provider",
                        entity_id="provider-7",
                        severity="high",
                        title="Outlier",
                        reasoning="Detected",
                        created_at=datetime.now(timezone.utc),
                    ),
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