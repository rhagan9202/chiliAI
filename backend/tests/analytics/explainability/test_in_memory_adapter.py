"""Tests for the in-memory explainability adapter."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.explainability.adapters.in_memory import InMemoryExplainabilityContextSource
from analytics.explainability.models import ExplanationContext, ExplanationItem, ExplanationSubgraph
from shared.types import Alert


def test_in_memory_context_source_returns_seeded_context() -> None:
    context = ExplanationContext(
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
            )
        ],
        subgraph=ExplanationSubgraph(node_ids=["provider-7"], edge_ids=[]),
        confidence=0.91,
    )
    source = InMemoryExplainabilityContextSource(contexts=[context])

    loaded = source.load_context(knowledge_base_id="kb-1", alert_id="alert-1")

    assert loaded == context