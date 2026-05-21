"""Investigation API router — entity detail, neighborhood, and search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.middleware.rbac import require_role
from config.schema import DomainConfig
from graph.protocols import GraphServiceProtocol
from graph.service_models import (
    EntityDetailResponse,
    EntitySearchResponse,
    NeighborhoodResponse,
)
from shared.kb_scope import KnowledgeBaseExistenceCheck, resolve_kb_scope

__all__ = ["get_graph_service", "router"]


def get_graph_service() -> GraphServiceProtocol:
    """Default graph service factory; tests override via ``dependency_overrides``."""
    from api.dependencies import get_graph_service as application_get_graph_service

    return application_get_graph_service()


def get_domain_config() -> DomainConfig:
    """Domain config provider; tests override via ``dependency_overrides``."""
    from api.dependencies import get_domain_config as application_get_domain_config

    return application_get_domain_config()


def get_knowledge_base_repository() -> KnowledgeBaseExistenceCheck:
    """KB repository provider; tests override via ``dependency_overrides``."""
    from api.dependencies import get_knowledge_base_repository as application_get_kb_repo

    return application_get_kb_repo()


router = APIRouter(prefix="/investigation", tags=["investigation"])


@router.get(
    "/entities/{entity_id}",
    response_model=EntityDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def read_entity(
    entity_id: str,
    kb_id: str = Query(..., description="Knowledge base identifier."),
    domain_config: DomainConfig = Depends(get_domain_config),
    kb_repository: KnowledgeBaseExistenceCheck = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
) -> EntityDetailResponse:
    """Return a single entity from the knowledge base or 404 if unknown."""
    kb_ids = resolve_kb_scope(kb_id, domain_config, kb_repository)
    entity = graph_service.get_entity(kb_ids, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found in knowledge base '{kb_id}'.",
        )
    return EntityDetailResponse(entity=entity)


@router.get(
    "/entities/{entity_id}/neighborhood",
    response_model=NeighborhoodResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def read_entity_neighborhood(
    entity_id: str,
    kb_id: str = Query(..., description="Knowledge base identifier."),
    depth: int = Query(default=2, ge=1, le=5, description="Traversal depth (1-5)."),
    domain_config: DomainConfig = Depends(get_domain_config),
    kb_repository: KnowledgeBaseExistenceCheck = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
) -> NeighborhoodResponse:
    """Return the neighborhood subgraph around an entity up to ``depth`` hops."""
    kb_ids = resolve_kb_scope(kb_id, domain_config, kb_repository)
    if graph_service.get_entity(kb_ids, entity_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found in knowledge base '{kb_id}'.",
        )
    subgraph = graph_service.query_neighborhood(kb_id, entity_id, depth)
    return NeighborhoodResponse(
        center_entity_id=entity_id,
        entities=subgraph.entities,
        relationships=subgraph.relationships,
    )


@router.get(
    "/search",
    response_model=EntitySearchResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def search_entities(
    kb_id: str = Query(..., description="Knowledge base identifier."),
    q: str = Query(..., min_length=1, description="Property substring to match."),
    limit: int = Query(default=20, ge=1, le=500, description="Maximum items returned."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
    domain_config: DomainConfig = Depends(get_domain_config),
    kb_repository: KnowledgeBaseExistenceCheck = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
) -> EntitySearchResponse:
    """Return entities matching ``q`` paginated by ``limit`` and ``offset``."""
    kb_ids = resolve_kb_scope(kb_id, domain_config, kb_repository)
    items = graph_service.search_entities(kb_ids, q, limit, offset)
    return EntitySearchResponse(items=items, total=len(items))
