"""In-memory evidence-pack repository for tests and local scaffolding."""

from __future__ import annotations

from analytics.explainability.repository import EvidencePackRepository
from shared.types import EvidencePack

__all__ = ["InMemoryEvidencePackRepository"]


class InMemoryEvidencePackRepository(EvidencePackRepository):
    """Persist evidence packs in a process-local dict keyed by (kb, pack id)."""

    def __init__(self) -> None:
        self._packs: dict[tuple[str, str], EvidencePack] = {}

    def put(self, knowledge_base_id: str, pack: EvidencePack) -> None:
        self._packs[(knowledge_base_id, pack.id)] = pack

    def get(self, knowledge_base_id: str, evidence_pack_id: str) -> EvidencePack | None:
        return self._packs.get((knowledge_base_id, evidence_pack_id))

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._packs if key[0] == knowledge_base_id]
        for key in keys:
            del self._packs[key]
        return len(keys)
