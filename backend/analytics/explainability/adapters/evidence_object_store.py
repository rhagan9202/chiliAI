"""Object-store-backed evidence-pack repository.

Packs are serialized to JSON under ``knowledgebases/{kb}/evidence/{id}.json``
so they are durable across the API and worker containers, alongside the
other object-store-backed repositories in this codebase (e.g. the KB
metadata store, ``knowledgebases/adapters/object_store.py``, and the GNN
cluster store, ``analytics/gnn/adapters/cluster_store.py``).
"""

from __future__ import annotations

from analytics.explainability.repository import EvidencePackRepository
from shared.protocols import ObjectStoreProtocol
from shared.types import EvidencePack

__all__ = ["ObjectStoreEvidencePackRepository"]


class ObjectStoreEvidencePackRepository(EvidencePackRepository):
    """Persist evidence packs as per-pack JSON objects in object storage."""

    def __init__(self, object_store: ObjectStoreProtocol) -> None:
        self._object_store = object_store

    def put(self, knowledge_base_id: str, pack: EvidencePack) -> None:
        self._object_store.put_bytes(
            self._key(knowledge_base_id, pack.id),
            pack.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={"record_type": "evidence_pack"},
        )

    def get(self, knowledge_base_id: str, evidence_pack_id: str) -> EvidencePack | None:
        key = self._key(knowledge_base_id, evidence_pack_id)
        if not self._object_store.exists(key):
            return None
        stored = self._object_store.get_bytes(key)
        return EvidencePack.model_validate_json(stored.content)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = self._object_store.list_keys(self._prefix(knowledge_base_id))
        for key in keys:
            self._object_store.delete(key)
        return len(keys)

    @staticmethod
    def _prefix(knowledge_base_id: str) -> str:
        return f"knowledgebases/{knowledge_base_id}/evidence/"

    @classmethod
    def _key(cls, knowledge_base_id: str, evidence_pack_id: str) -> str:
        return f"{cls._prefix(knowledge_base_id)}{evidence_pack_id}.json"
