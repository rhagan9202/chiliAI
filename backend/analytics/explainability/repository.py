"""Persistence protocol for generated evidence packs.

The worker persists an :class:`~shared.types.EvidencePack` after the
explainability stage produces it; the API reads it back to serve
``GET /evidence-packs/{id}``. Packs are KB-scoped so isolation holds at the
repository boundary (REQ-AUTH-006).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.types import EvidencePack


@runtime_checkable
class EvidencePackRepository(Protocol):
    """Store and retrieve generated evidence packs, scoped by knowledge base."""

    def put(self, knowledge_base_id: str, pack: EvidencePack) -> None: ...

    def get(self, knowledge_base_id: str, evidence_pack_id: str) -> EvidencePack | None: ...

    def delete_by_kb(self, knowledge_base_id: str) -> int: ...


__all__ = ["EvidencePackRepository"]
