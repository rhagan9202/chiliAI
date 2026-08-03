"""Evidence pack router exposing investigation evidence read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from api.contracts import (
    EvidencePackExportResponse,
    EvidencePackResponse,
    EvidenceProvenanceListResponse,
)
from api.dependencies import (
    build_evidence_provenance_response,
    get_evidence_pack_export_payload,
    get_evidence_pack_payload,
    get_evidence_provenance_payload,
    get_evidence_provenance_repository,
)
from analytics.explainability.provenance import EvidenceProvenanceRepository
from api.middleware.rbac import require_role

__all__ = ["kb_router", "router"]

router = APIRouter(prefix="/evidence-packs", tags=["evidence"])
kb_router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/evidence-packs",
    tags=["evidence"],
)


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


@router.get(
    "/{evidence_pack_id}/provenance",
    response_model=EvidenceProvenanceListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_evidence_pack_provenance(
    provenance: EvidenceProvenanceListResponse = Depends(
        get_evidence_provenance_payload
    ),
) -> EvidenceProvenanceListResponse:
    """Return structured provenance references for one evidence pack."""
    return provenance


@kb_router.get(
    "/{evidence_pack_id}/provenance",
    response_model=EvidenceProvenanceListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_kb_evidence_pack_provenance(
    knowledge_base_id: str = Path(..., min_length=1),
    evidence_pack_id: str = Path(..., description="Evidence pack identifier."),
    repository: EvidenceProvenanceRepository = Depends(
        get_evidence_provenance_repository
    ),
) -> EvidenceProvenanceListResponse:
    """Return structured provenance references for one KB-scoped evidence pack."""

    return build_evidence_provenance_response(
        knowledge_base_id=knowledge_base_id,
        evidence_pack_id=evidence_pack_id,
        repository=repository,
    )


@router.get(
    "/{evidence_pack_id}/export",
    response_model=EvidencePackExportResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def export_evidence_pack(
    export: EvidencePackExportResponse = Depends(get_evidence_pack_export_payload),
) -> EvidencePackExportResponse:
    """Return a downloadable JSON or Markdown rendering of one evidence pack.

    Same gate as reading the pack: an export is a projection of what the caller
    can already see, not a new disclosure.
    """
    return export
