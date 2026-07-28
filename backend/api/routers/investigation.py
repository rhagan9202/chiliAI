"""Investigation API router — entity detail, neighborhood, and search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.contracts import EntityLocationListResponse, EntityLocationResponse
from api.middleware.rbac import require_role
from config.schema import DomainConfig, ValidationConfig
from graph.protocols import GraphServiceProtocol
from graph.service_models import (
    EntityDetailResponse,
    EntitySearchResponse,
    NeighborhoodResponse,
)
from shared.kb_scope import KnowledgeBaseExistenceCheck, resolve_kb_scope
from shared.validation import validate_query_length

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


# Pagination for the cross-KB scan; workspaces hold tens of KBs, not thousands.
_KB_SCAN_PAGE_SIZE = 200

router = APIRouter(prefix="/investigation", tags=["investigation"])


@router.get(
    "/entities/{entity_id}/locate",
    response_model=EntityLocationListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def locate_entity(
    entity_id: str,
    kb_repository: KnowledgeBaseExistenceCheck = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
) -> EntityLocationListResponse:
    """Return the knowledge bases holding ``entity_id``.

    A deep link that arrives without ``?kb=`` used to resolve against whatever
    the workspace happened to point at and fail (UXA-104). This lets the UI
    offer "this entity is in <KB> — switch and open it", and to say plainly
    when it exists nowhere. An empty list is the honest answer to the latter,
    not a 404: the question "where does this live" was answered.
    """
    listing = getattr(kb_repository, "list", None)
    if listing is None:
        return EntityLocationListResponse(items=[])

    located: list[EntityLocationResponse] = []
    offset = 0
    while True:
        page, total = listing(limit=_KB_SCAN_PAGE_SIZE, offset=offset)
        for knowledge_base in page:
            # get_entity takes a KB id list, so this is one keyed read per KB
            # rather than a scan of each graph.
            if graph_service.get_entity([knowledge_base.id], entity_id) is not None:
                located.append(
                    EntityLocationResponse(
                        knowledge_base_id=knowledge_base.id,
                        knowledge_base_name=knowledge_base.name,
                    )
                )
        offset += len(page)
        if not page or offset >= total:
            break
    return EntityLocationListResponse(items=located)


@router.get(
    "/entities/{entity_id}",
    response_model=EntityDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def read_entity(
    entity_id: str,
    kb_id: str = Query(..., alias="knowledge_base_id", description="Knowledge base identifier."),
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
    kb_id: str = Query(..., alias="knowledge_base_id", description="Knowledge base identifier."),
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
    # query_neighborhood is single-graph by spec — traversal cannot span KBs because
    # cross-KB relationships are not stored. An entity found in the reference KB
    # via the existence check above will return an empty neighborhood here.
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
    kb_id: str = Query(..., alias="knowledge_base_id", description="Knowledge base identifier."),
    q: str = Query(..., min_length=1, description="Property substring to match."),
    limit: int = Query(default=20, ge=1, le=500, description="Maximum items returned."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
    domain_config: DomainConfig = Depends(get_domain_config),
    kb_repository: KnowledgeBaseExistenceCheck = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
) -> EntitySearchResponse:
    """Return entities matching ``q`` paginated by ``limit`` and ``offset``."""
    validation = domain_config.validation or ValidationConfig()
    try:
        cleaned_query = validate_query_length(q, validation.max_query_length)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    kb_ids = resolve_kb_scope(kb_id, domain_config, kb_repository)
    items = graph_service.search_entities(kb_ids, cleaned_query, limit, offset)
    return EntitySearchResponse(items=items, total=len(items))
