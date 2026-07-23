"""Tests for the deterministic narrative generator adapter."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.explainability.adapters.deterministic import DeterministicNarrativeGenerator
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from shared.types import Alert


def _context(items: list[ExplanationItem]) -> ExplanationContext:
    return ExplanationContext(
        knowledge_base_id="kb-1",
        alert=Alert(
            id="a-1",
            entity_type="provider",
            entity_id="p-1",
            severity="high",
            title="t",
            reasoning="r",
            created_at=datetime.now(tz=timezone.utc),
        ),
        explanation_items=items,
        subgraph=ExplanationSubgraph(node_ids=["p-1"]),
        confidence=0.8,
        scores={"overall": 0.8},
    )


def _item(source_type: str, rationale: str, score: float = 0.5) -> ExplanationItem:
    return ExplanationItem(
        source_id=f"src-{rationale}",
        source_type=source_type,
        quote="q",
        rationale=rationale,
        score=score,
    )


class TestDeterministicNarrativeGenerator:
    def test_groups_by_source_type_in_first_seen_order(self) -> None:
        items = [_item("risk_factor", "one"), _item("peer", "two"), _item("risk_factor", "three")]
        narrative = DeterministicNarrativeGenerator().summarize(context=_context(items), items=items)
        assert [s.heading for s in narrative.sections] == ["Risk Factor", "Peer"]
        assert narrative.sections[0].body == "one three"
        assert narrative.sections[0].evidence_refs == ["src-one", "src-three"]

    def test_summary_is_space_joined_rationales(self) -> None:
        items = [_item("risk_factor", "one"), _item("peer", "two")]
        narrative = DeterministicNarrativeGenerator().summarize(context=_context(items), items=items)
        assert narrative.summary == "one two"
