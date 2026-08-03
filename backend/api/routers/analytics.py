"""Analytics API endpoints for risk scores, timeseries, and GNN clusters."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service_models import GnnClusterRequest, GnnClusterResponse
from analytics.risk.projection_service import (
    RiskProjectionRebuildSourceProtocol,
    RiskProjectionService,
)
from analytics.risk.projections import (
    RiskProjectionQuery,
    RiskProjectionRepositoryProtocol,
    RiskProjectionRow,
)
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service_models import RiskScoreListRequest, RiskScoreListResponse
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service_models import (
    MetricTimeseriesResponse,
    TimeseriesQueryRequest,
)
from api.contracts import (
    AnalyticsOverviewResponse,
    EntityTimeseriesResponse,
    RiskProjectionItemResponse,
    RiskProjectionLevelValue,
    RiskProjectionListResponse,
    RiskProjectionRebuildRequest,
    RiskProjectionRebuildResponse,
    RiskProjectionStatusValue,
    RiskScoreResponse,
)
from api.dependencies import (
    get_analytics_overview_payload,
    get_gnn_service,
    get_risk_projection_repository,
    get_risk_projection_rebuild_source,
    get_risk_projection_service,
    get_risk_score_payload,
    get_risk_service,
    get_timeseries_payload,
    get_timeseries_service,
)
from api.middleware.rbac import require_role

__all__ = ["router"]


router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get(
    "/risk-scores",
    response_model=RiskScoreListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_risk_scores(
    kb_id: str = Query(..., alias="knowledge_base_id", min_length=1),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=20, gt=0, le=500),
    risk_service: RiskServiceProtocol = Depends(get_risk_service),
) -> RiskScoreListResponse:
    """Return ranked risk scores for entities in a knowledge base."""
    request = RiskScoreListRequest(
        knowledge_base_id=kb_id,
        entity_type=entity_type,
        limit=limit,
    )
    return risk_service.list_scores(request)


@router.get(
    "/risk-projections",
    response_model=RiskProjectionListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_risk_projections(
    kb_id: str = Query(..., alias="knowledge_base_id", min_length=1),
    entity_type: str | None = Query(default=None),
    risk_level: RiskProjectionLevelValue | None = Query(default=None),
    typology_id: str | None = Query(default=None),
    status: RiskProjectionStatusValue | None = Query(default=None),
    max_score_age_hours: int | None = Query(default=None, gt=0),
    as_of: datetime | None = Query(default=None),
    limit: int = Query(default=20, gt=0, le=500),
    offset: int = Query(default=0, ge=0),
    repository: RiskProjectionRepositoryProtocol = Depends(get_risk_projection_repository),
) -> RiskProjectionListResponse:
    """Return projection-backed risk rows for queue/dashboard consumers."""
    query = RiskProjectionQuery(
        knowledge_base_id=kb_id,
        entity_type=entity_type,
        risk_level=risk_level,
        typology_id=typology_id,
        status=status,
        max_score_age_hours=max_score_age_hours,
        as_of=_projection_as_of(as_of),
        limit=limit,
        offset=offset,
    )
    page = repository.list(query)
    return RiskProjectionListResponse(
        knowledge_base_id=kb_id,
        items=[_risk_projection_response(row) for row in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/risk-projections/rebuild",
    response_model=RiskProjectionRebuildResponse,
    dependencies=[Depends(require_role("analyst"))],
)
def rebuild_risk_projections(
    payload: RiskProjectionRebuildRequest,
    rebuild_source: RiskProjectionRebuildSourceProtocol | None = Depends(
        get_risk_projection_rebuild_source
    ),
    projection_service: RiskProjectionService = Depends(get_risk_projection_service),
) -> RiskProjectionRebuildResponse:
    """Run the configured in-process risk projection rebuild seam for one KB."""
    if rebuild_source is None:
        raise HTTPException(
            status_code=503,
            detail="Risk projection rebuild source is not configured.",
        )
    result = projection_service.rebuild_knowledge_base(
        payload.knowledge_base_id,
        rebuild_source.load_projection_rows(payload.knowledge_base_id),
    )
    return RiskProjectionRebuildResponse(
        knowledge_base_id=payload.knowledge_base_id,
        changed=result.changed,
        deleted=result.deleted,
        upserted=result.upserted,
        status="completed",
    )


@router.get(
    "/timeseries",
    response_model=MetricTimeseriesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def query_timeseries(
    kb_id: str = Query(..., alias="knowledge_base_id", min_length=1),
    metric: str = Query(..., min_length=1),
    start: datetime = Query(...),
    end: datetime = Query(...),
    timeseries_service: TimeseriesServiceProtocol = Depends(get_timeseries_service),
) -> MetricTimeseriesResponse:
    """Return data points for one metric over a bounded time range."""
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    request = TimeseriesQueryRequest(
        knowledge_base_id=kb_id,
        metric_name=metric,
        start=start,
        end=end,
    )
    return timeseries_service.query_metric(request)


@router.get(
    "/gnn/clusters",
    response_model=GnnClusterResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_gnn_clusters(
    kb_id: str = Query(..., alias="knowledge_base_id", min_length=1),
    gnn_service: GnnServiceProtocol = Depends(get_gnn_service),
) -> GnnClusterResponse:
    """Return GNN-derived clusters for a knowledge base.

    Returns an empty list when the GNN capability is disabled in config.
    """
    return gnn_service.list_clusters(GnnClusterRequest(knowledge_base_id=kb_id))


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_analytics_overview(
    payload: AnalyticsOverviewResponse = Depends(get_analytics_overview_payload),
) -> AnalyticsOverviewResponse:
    """Return dashboard overview metrics for the analytics page."""
    return payload


@router.get(
    "/risk-scores/{entity_id}",
    response_model=RiskScoreResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_risk_score(
    payload: RiskScoreResponse = Depends(get_risk_score_payload),
) -> RiskScoreResponse:
    """Return the risk score breakdown for one entity."""
    return payload


@router.get(
    "/timeseries/{entity_id}",
    response_model=EntityTimeseriesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_entity_timeseries(
    payload: EntityTimeseriesResponse = Depends(get_timeseries_payload),
) -> EntityTimeseriesResponse:
    """Return chartable time-series points for one entity."""
    return payload


def _projection_as_of(as_of: datetime | None) -> datetime:
    if as_of is None:
        return datetime.now(timezone.utc)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="as_of must include timezone information.",
        )
    return as_of


def _risk_projection_response(row: RiskProjectionRow) -> RiskProjectionItemResponse:
    return RiskProjectionItemResponse(
        knowledge_base_id=row.knowledge_base_id,
        entity_id=row.entity_id,
        entity_type=row.entity_type,
        overall_score=row.overall_score,
        risk_level=row.risk_level,
        top_typology_ids=list(row.top_typology_ids),
        alert_ids=list(row.alert_ids),
        case_ids=list(row.case_ids),
        evidence_pack_ids=list(row.evidence_pack_ids),
        score_run_id=row.score_run_id,
        model_version=row.model_version,
        catalog_version=row.catalog_version,
        scored_at=row.scored_at,
        updated_at=row.updated_at,
        status=row.status,
    )
