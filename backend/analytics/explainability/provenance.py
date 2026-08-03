"""Evidence provenance repository seam.

The first SAFE-CMS-004 persistence slice stores provenance inside the durable
``EvidencePack`` artifact. This adapter gives API/workflow callers a narrow
query boundary that can later be backed by a normalized SQL table.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.explainability.repository import EvidencePackRepository
from shared.types import EvidenceProvenanceReference


@runtime_checkable
class EvidenceProvenanceRepository(Protocol):
    """Query and replace provenance references for one evidence pack."""

    def list_for_evidence_pack(
        self,
        knowledge_base_id: str,
        evidence_pack_id: str,
    ) -> list[EvidenceProvenanceReference] | None: ...

    def replace_for_evidence_pack(
        self,
        knowledge_base_id: str,
        evidence_pack_id: str,
        refs: list[EvidenceProvenanceReference],
    ) -> bool: ...


class EvidencePackProvenanceRepository:
    """Evidence provenance adapter backed by persisted ``EvidencePack`` rows."""

    def __init__(self, evidence_pack_repository: EvidencePackRepository) -> None:
        self._packs = evidence_pack_repository

    def list_for_evidence_pack(
        self,
        knowledge_base_id: str,
        evidence_pack_id: str,
    ) -> list[EvidenceProvenanceReference] | None:
        pack = self._packs.get(knowledge_base_id, evidence_pack_id)
        if pack is None:
            return None
        return [ref.model_copy(deep=True) for ref in pack.provenance]

    def replace_for_evidence_pack(
        self,
        knowledge_base_id: str,
        evidence_pack_id: str,
        refs: list[EvidenceProvenanceReference],
    ) -> bool:
        pack = self._packs.get(knowledge_base_id, evidence_pack_id)
        if pack is None:
            return False
        updated = pack.model_copy(update={"provenance": refs}, deep=True)
        self._packs.put(knowledge_base_id, updated)
        return True


__all__ = [
    "EvidencePackProvenanceRepository",
    "EvidenceProvenanceRepository",
]
