"""Focused evidence-pack payload mapper tests."""

from __future__ import annotations

from api.dependencies import _evidence_pack_to_response
from shared.types import EvidencePack, EvidenceProvenanceReference


def test_evidence_pack_response_includes_structured_provenance() -> None:
    pack = EvidencePack(
        id="ev-1",
        alert_id="al-1",
        reasoning="Elevated peer deviation.",
        subgraph_nodes=["provider-1"],
        subgraph_edges=[],
        confidence=0.8,
        provenance=[
            EvidenceProvenanceReference(
                reference_type="feature_value",
                reference_id="feature:claim_volume_z:provider-1",
                label="Claim volume z-score",
                source_system="cms-claims",
                source_version="2026-08-demo",
                transformation_version="peerstats-zscore-v1",
                confidence=0.8,
                route_target="/knowledgebases/kb-1/entities/provider-1",
                metadata={"score_run_id": "score-run-1"},
            )
        ],
    )

    payload = _evidence_pack_to_response(pack).model_dump(mode="json")

    assert payload["provenance"] == [
        {
            "reference_type": "feature_value",
            "reference_id": "feature:claim_volume_z:provider-1",
            "label": "Claim volume z-score",
            "source_system": "cms-claims",
            "source_version": "2026-08-demo",
            "transformation_version": "peerstats-zscore-v1",
            "confidence": 0.8,
            "route_target": "/knowledgebases/kb-1/entities/provider-1",
            "metadata": {"score_run_id": "score-run-1"},
        }
    ]


def test_evidence_pack_response_defaults_legacy_provenance_to_empty() -> None:
    pack = EvidencePack(
        id="ev-legacy",
        alert_id="al-1",
        reasoning="Legacy pack.",
        subgraph_nodes=["provider-1"],
        subgraph_edges=[],
        confidence=0.8,
    )

    payload = _evidence_pack_to_response(pack).model_dump(mode="json")

    assert payload["provenance"] == []
