"""Analytics API endpoints for risk scores, timeseries, and GNN clusters."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service_models import GnnClusterRequest, GnnClusterResponse
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
    RiskScoreResponse,
)
from api.dependencies import (
    get_analytics_overview_payload,
    get_gnn_service,
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
    kb_id: str = Query(..., min_length=1),
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
    "/timeseries",
    response_model=MetricTimeseriesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def query_timeseries(
    kb_id: str = Query(..., min_length=1),
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
    kb_id: str = Query(..., min_length=1),
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
