"""Evidence pack router exposing investigation evidence read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import EvidencePackResponse
from api.dependencies import get_evidence_pack_payload
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/evidence-packs", tags=["evidence"])


@router.get(
    "/{evidence_pack_id}",
    response_model=EvidencePackResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_evidence_pack(
    evidence_pack: EvidencePackResponse = Depends(get_evidence_pack_payload),
) -> EvidencePackResponse:
    """Return one evidence pack read model."""
    return evidence_pack