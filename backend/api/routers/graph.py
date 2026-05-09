"""Investigation graph router exposing entity read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import GraphEntityDetailResponse
from api.dependencies import get_graph_entity_detail_payload

__all__ = ["router"]

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/entities/{entity_id}", response_model=GraphEntityDetailResponse)
async def get_entity_detail(
    entity_detail: GraphEntityDetailResponse = Depends(get_graph_entity_detail_payload),
) -> GraphEntityDetailResponse:
    """Return investigation detail for one entity."""
    return entity_detail