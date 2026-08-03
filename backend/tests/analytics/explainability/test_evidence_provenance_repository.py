"""Evidence provenance query seam tests."""

from __future__ import annotations

from analytics.explainability.adapters.evidence_in_memory import (
    InMemoryEvidencePackRepository,
)
from analytics.explainability.provenance import EvidencePackProvenanceRepository
from shared.types import EvidencePack, EvidenceProvenanceReference


def _reference(reference_id: str = "feature:claim_volume_z:provider-1") -> EvidenceProvenanceReference:
    return EvidenceProvenanceReference(
        reference_type="feature_value",
        reference_id=reference_id,
        label="Claim volume z-score",
        source_system="cms-claims",
        source_version="2026-08-demo",
        transformation_version="peerstats-zscore-v1",
        confidence=0.8,
        route_target="/knowledgebases/kb-1/entities/provider-1",
        metadata={"score_run_id": "score-run-1"},
    )


def _pack(pack_id: str = "ev-1") -> EvidencePack:
    return EvidencePack(
        id=pack_id,
        alert_id="al-1",
        reasoning="Elevated peer deviation.",
        subgraph_nodes=["provider-1"],
        subgraph_edges=[],
        confidence=0.8,
        provenance=[_reference()],
    )


def test_lists_provenance_refs_from_persisted_evidence_pack() -> None:
    packs = InMemoryEvidencePackRepository()
    packs.put("kb-1", _pack())
    repository = EvidencePackProvenanceRepository(packs)

    refs = repository.list_for_evidence_pack("kb-1", "ev-1")

    assert refs == [_reference()]


def test_missing_pack_returns_none() -> None:
    repository = EvidencePackProvenanceRepository(InMemoryEvidencePackRepository())

    assert repository.list_for_evidence_pack("kb-1", "missing") is None


def test_replaces_provenance_refs_without_changing_other_pack_fields() -> None:
    packs = InMemoryEvidencePackRepository()
    packs.put("kb-1", _pack())
    repository = EvidencePackProvenanceRepository(packs)
    replacement = _reference("graph:edge:rel-1").model_copy(
        update={"reference_type": "graph_edge", "label": "Submitted claim edge"}
    )

    replaced = repository.replace_for_evidence_pack("kb-1", "ev-1", [replacement])

    stored = packs.get("kb-1", "ev-1")
    assert replaced is True
    assert stored is not None
    assert stored.reasoning == "Elevated peer deviation."
    assert stored.provenance == [replacement]
