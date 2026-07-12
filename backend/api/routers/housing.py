"""Air Force housing dashboard API endpoints.

Thin HTTP layer over :mod:`api._housing_read_model`, which computes the
executive overview and installation list/map read models from the knowledge
base's ingested feed records — the same rows the scorecard evaluator
consumes. See that module for the aggregation and status-derivation rules.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from api._housing_read_model import (
    build_housing_installations,
    build_housing_overview,
)
from api.contracts import HousingInstallationsResponse, HousingOverviewResponse
from api.dependencies import (
    RecordFeedSourceLoader,
    get_domain_config,
    get_knowledge_base_repository,
    get_source_record_loader,
)
from api.middleware.rbac import require_role
from config.schema import DomainConfig
from knowledgebases.protocols import KnowledgeBaseRepository

__all__ = ["router"]


router = APIRouter(prefix="/housing", tags=["housing"])


@router.get(
    "/overview",
    response_model=HousingOverviewResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def get_overview(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    knowledge_base_id: str | None = Query(
        default=None,
        description="Knowledge base to aggregate; defaults to the newest KB of the active domain.",
    ),
    config: DomainConfig = Depends(get_domain_config),
    loader: RecordFeedSourceLoader = Depends(get_source_record_loader),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
) -> HousingOverviewResponse:
    """Return the executive housing KPI model computed from ingested records."""
    return build_housing_overview(
        knowledge_base_id=knowledge_base_id,
        period_start=period_start,
        period_end=period_end,
        config=config,
        loader=loader,
        kb_repository=kb_repository,
    )


@router.get(
    "/installations",
    response_model=HousingInstallationsResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_installations(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    knowledge_base_id: str | None = Query(
        default=None,
        description="Knowledge base to aggregate; defaults to the newest KB of the active domain.",
    ),
    config: DomainConfig = Depends(get_domain_config),
    loader: RecordFeedSourceLoader = Depends(get_source_record_loader),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
) -> HousingInstallationsResponse:
    """Return the installation list and map computed from ingested records.

    Installations without resolvable coordinates appear in ``items`` but not
    in ``map_points`` — surfaced as location-pending, never silently dropped.
    """
    return build_housing_installations(
        knowledge_base_id=knowledge_base_id,
        period_start=period_start,
        period_end=period_end,
        config=config,
        loader=loader,
        kb_repository=kb_repository,
    )
