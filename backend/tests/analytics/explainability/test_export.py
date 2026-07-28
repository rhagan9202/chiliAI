"""Tests for the evidence pack Markdown export (UXA-405)."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.explainability.export import humanize_score_name, render_evidence_markdown
from shared.types import EvidenceNarrativeSection, EvidencePack, FeatureAttribution


def _pack(**overrides: object) -> EvidencePack:
    defaults: dict[str, object] = {
        "id": "ev-1",
        "alert_id": "alert-1",
        "reasoning": "Billing volume is far above the provider's peer group.",
        "subgraph_nodes": ["provider-1", "claim-9"],
        "subgraph_edges": ["submitted_by-1"],
        "confidence": 0.87,
        "created_at": datetime(2026, 7, 1, 12, 30, tzinfo=timezone.utc),
        "scores": {"peer_deviation": 3.4, "risk": 0.91},
        "source_documents": ["doc-policy-1"],
        "attribution": [
            FeatureAttribution(
                feature_name="billed_amount",
                contribution=0.42,
                rationale="4x the peer median.",
            ),
            FeatureAttribution(feature_name="claim_count", contribution=-0.08),
        ],
        "narrative_sections": [
            EvidenceNarrativeSection(
                heading="What happened",
                body="The provider submitted numerous high-value claims.",
                evidence_refs=["claim-9"],
            )
        ],
    }
    defaults.update(overrides)
    return EvidencePack.model_validate(defaults)


class TestHumanizeScoreName:
    def test_matches_the_frontend_rule(self) -> None:
        # EvidencePackViewer.tsx humanizeScoreName does exactly this; the export
        # must read like the screen it came from.
        assert humanize_score_name("peer_deviation") == "Peer deviation"
        assert humanize_score_name("risk-score") == "Risk score"
        assert humanize_score_name("risk") == "Risk"

    def test_survives_an_empty_key(self) -> None:
        assert humanize_score_name("") == ""
        assert humanize_score_name("   ") == ""


class TestRenderEvidenceMarkdown:
    def test_renders_every_section_of_a_full_pack(self) -> None:
        rendered = render_evidence_markdown(_pack())

        assert rendered.startswith("# Evidence pack ev-1")
        assert "- **Alert:** `alert-1`" in rendered
        assert "2026-07-01T12:30:00+00:00" in rendered
        assert "**Confidence:** 87%" in rendered
        assert "## Reasoning" in rendered
        assert "peer group" in rendered
        assert "## What happened" in rendered
        assert "_Refs: claim-9_" in rendered
        assert "**Peer deviation:** 3.4" in rendered
        assert "## Source documents" in rendered
        assert "`doc-policy-1`" in rendered
        assert "- **Nodes:** 2" in rendered
        assert "`submitted_by-1`" in rendered
        assert rendered.endswith("\n")

    def test_uses_the_alert_title_as_the_heading_when_given(self) -> None:
        rendered = render_evidence_markdown(_pack(), alert_title="Elevated risk: Redwood DME")

        assert rendered.startswith("# Elevated risk: Redwood DME")

    def test_keeps_the_sign_on_a_negative_contribution(self) -> None:
        # A factor that pushed the score down is part of the explanation.
        rendered = render_evidence_markdown(_pack())

        assert "**Claim count:** -0.080" in rendered
        assert "**Billed amount:** +0.420 — 4x the peer median." in rendered

    def test_omits_empty_sections_rather_than_rendering_bare_headings(self) -> None:
        rendered = render_evidence_markdown(
            _pack(
                reasoning="",
                scores={},
                source_documents=[],
                attribution=[],
                narrative_sections=[],
                subgraph_nodes=[],
                subgraph_edges=[],
            )
        )

        assert "## Reasoning" not in rendered
        assert "## Scores" not in rendered
        assert "## Source documents" not in rendered
        assert "## Contributing factors" not in rendered
        assert "## Subgraph" not in rendered
        # The identifying header survives, so an empty pack still exports.
        assert "- **Evidence pack:** `ev-1`" in rendered

    def test_orders_scores_deterministically(self) -> None:
        # Two exports of one pack must be byte-identical; dict order is not a
        # guarantee worth relying on.
        first = render_evidence_markdown(_pack(scores={"b": 1.0, "a": 2.0}))
        second = render_evidence_markdown(_pack(scores={"a": 2.0, "b": 1.0}))

        assert first == second
        assert first.index("**A:**") < first.index("**B:**")
