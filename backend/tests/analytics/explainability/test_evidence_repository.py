"""Tests for the evidence-pack repository adapters (BL-005)."""

from __future__ import annotations

import pytest

from analytics.explainability.adapters.evidence_in_memory import (
    InMemoryEvidencePackRepository,
)
from analytics.explainability.adapters.evidence_object_store import (
    ObjectStoreEvidencePackRepository,
)
from analytics.explainability.repository import EvidencePackRepository
from shared.types import EvidencePack
from storage.adapters.in_memory import InMemoryObjectStore


def _pack(pack_id: str = "ev-1", alert_id: str = "al-1") -> EvidencePack:
    return EvidencePack(
        id=pack_id,
        alert_id=alert_id,
        reasoning="reasoning",
        subgraph_nodes=["provider-1", "claim-1"],
        subgraph_edges=["rel-1"],
        confidence=0.82,
        scores={"overall": 0.82},
    )


def _repositories() -> list[EvidencePackRepository]:
    return [
        InMemoryEvidencePackRepository(),
        ObjectStoreEvidencePackRepository(InMemoryObjectStore()),
    ]


@pytest.mark.parametrize("repository", _repositories())
def test_put_then_get_roundtrip(repository: EvidencePackRepository) -> None:
    repository.put("kb-1", _pack())

    fetched = repository.get("kb-1", "ev-1")

    assert fetched is not None
    assert fetched.id == "ev-1"
    assert fetched.subgraph_nodes == ["provider-1", "claim-1"]
    assert fetched.scores == {"overall": 0.82}


@pytest.mark.parametrize("repository", _repositories())
def test_get_missing_returns_none(repository: EvidencePackRepository) -> None:
    assert repository.get("kb-1", "missing") is None


@pytest.mark.parametrize("repository", _repositories())
def test_kb_isolation(repository: EvidencePackRepository) -> None:
    repository.put("kb-1", _pack())

    assert repository.get("kb-2", "ev-1") is None


@pytest.mark.parametrize("repository", _repositories())
def test_delete_by_kb(repository: EvidencePackRepository) -> None:
    repository.put("kb-1", _pack("ev-1"))
    repository.put("kb-1", _pack("ev-2"))
    repository.put("kb-2", _pack("ev-3"))

    removed = repository.delete_by_kb("kb-1")

    assert removed == 2
    assert repository.get("kb-1", "ev-1") is None
    assert repository.get("kb-2", "ev-3") is not None
