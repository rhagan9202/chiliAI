"""Tests for the explainability service."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.exceptions import ExplainabilityConfigurationError
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationLineage,
    ExplanationNarrative,
    ExplanationSubgraph,
    NarrativeSection,
)
from analytics.explainability.service import create_explainability_service
from analytics.explainability.service_models import ExplainabilityRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import ExplainabilityGeneratedEvent
from shared.types import Alert, EvidenceNarrativeSection, FeatureAttribution


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


class _StubNarrativeGenerator:
    """Fixed two-section narrative, independent of the items passed in."""

    def summarize(
        self, *, context: ExplanationContext, items: Sequence[ExplanationItem]
    ) -> ExplanationNarrative:
        return ExplanationNarrative(
            summary="stub composite summary",
            sections=[
                NarrativeSection(heading="First", body="first body", evidence_refs=["doc-1"]),
                NarrativeSection(heading="Second", body="second body", evidence_refs=["doc-2"]),
            ],
        )


class _StubLineageNarrativeGenerator(_StubNarrativeGenerator):
    model_name = "llm-model-from-generator"
    prompt_version = "prompt-from-generator-v1"


class _StubFeatureAttributor:
    """Fixed single-feature attribution, independent of the context passed in."""

    def attribute(self, *, context: ExplanationContext) -> list[FeatureAttribution]:
        return [FeatureAttribution(feature_name="risk", contribution=0.42, rationale="stub")]


def _single_item_context() -> ExplanationContext:
    return ExplanationContext(
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


def test_explainability_service_composes_injected_narrative_and_attribution() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(contexts=[_single_item_context()]),
        event_bus=event_bus,
        narrative_generator=_StubNarrativeGenerator(),
        feature_attributor=_StubFeatureAttributor(),
    )

    response = service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1"))
    pack = response.evidence_pack

    assert pack.reasoning == "stub composite summary"
    assert pack.narrative_sections == [
        EvidenceNarrativeSection(heading="First", body="first body", evidence_refs=["doc-1"]),
        EvidenceNarrativeSection(heading="Second", body="second body", evidence_refs=["doc-2"]),
    ]
    assert pack.attribution == [FeatureAttribution(feature_name="risk", contribution=0.42, rationale="stub")]


def test_explainability_service_generates_deterministic_provenance_refs() -> None:
    event_bus = InMemoryEventBus()
    context = _single_item_context().model_copy(
        update={
            "scores": {"overall": 0.5, "risk": 0.42},
            "lineage": ExplanationLineage(
                score_request_id="risk:corr-1:kb-1:provider-7",
                correlation_id="corr-1",
                workflow_id="workflow-1",
                model_version="risk-model-v1",
                prompt_version="evidence-prompt-v1",
            ),
        }
    )
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(contexts=[context]),
        event_bus=event_bus,
        narrative_generator=_StubNarrativeGenerator(),
        feature_attributor=_StubFeatureAttributor(),
    )

    response = service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1"))

    refs = {
        (reference.reference_type, reference.reference_id): reference
        for reference in response.evidence_pack.provenance
    }
    document_ref = refs[("document", "doc-1#evidence:0")]
    assert document_ref.route_target == "/knowledgebases/kb-1/documents/doc-1/preview"
    assert document_ref.metadata["rationale_snippet"] == "alpha"
    assert document_ref.metadata["rationale_length"] == 5
    assert ("graph_node", "provider-7") in refs
    assert ("risk_score", "risk:corr-1:kb-1:provider-7") in refs
    assert refs[("risk_score", "risk:corr-1:kb-1:provider-7")].metadata == {
        "overall": 0.5,
        "risk": 0.42,
    }
    assert ("feature_attribution", "risk") in refs
    assert ("narrative_section", "section:0:First") in refs
    assert ("correlation", "corr-1") in refs
    assert ("workflow", "workflow-1") in refs
    assert ("model_version", "risk-model-v1") in refs
    assert ("prompt_version", "evidence-prompt-v1") in refs


def test_explainability_service_keeps_same_document_evidence_refs_distinct() -> None:
    event_bus = InMemoryEventBus()
    long_rationale = "x" * 200
    context = _single_item_context().model_copy(
        update={
            "explanation_items": [
                ExplanationItem(
                    source_id="doc-1",
                    source_type="document",
                    quote="First quote",
                    rationale=long_rationale,
                    score=0.8,
                ),
                ExplanationItem(
                    source_id="doc-1",
                    source_type="document",
                    quote="Second quote",
                    rationale="second rationale",
                    score=0.7,
                ),
            ],
        }
    )
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(contexts=[context]),
        event_bus=event_bus,
    )

    response = service.generate(
        ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1", max_evidence_items=2)
    )

    document_refs = [
        reference
        for reference in response.evidence_pack.provenance
        if reference.reference_type == "document"
    ]
    assert [reference.reference_id for reference in document_refs] == [
        "doc-1#evidence:0",
        "doc-1#evidence:1",
    ]
    assert document_refs[0].metadata["rationale_length"] == 200
    assert document_refs[0].metadata["rationale_snippet"] == ("x" * 157) + "..."


def test_explainability_service_uses_generator_lineage_when_available() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(contexts=[_single_item_context()]),
        event_bus=event_bus,
        narrative_generator=_StubLineageNarrativeGenerator(),
    )

    response = service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1"))

    refs = {
        (reference.reference_type, reference.reference_id)
        for reference in response.evidence_pack.provenance
    }
    assert ("model_version", "llm-model-from-generator") in refs
    assert ("prompt_version", "prompt-from-generator-v1") in refs


def test_explainability_service_default_construction_has_empty_attribution() -> None:
    event_bus = InMemoryEventBus()
    service = create_explainability_service(
        InMemoryExplainabilityContextSource(contexts=[_single_item_context()]),
        event_bus=event_bus,
    )

    response = service.generate(ExplainabilityRequest(knowledge_base_id="kb-1", alert_id="alert-1"))
    pack = response.evidence_pack

    assert pack.attribution == []
    assert pack.reasoning == "alpha"
    assert pack.narrative_sections == [
        EvidenceNarrativeSection(heading="Document", body="alpha", evidence_refs=["doc-1"]),
    ]
