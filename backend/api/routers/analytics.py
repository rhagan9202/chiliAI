"""Analytics router exposing dashboard and investigation read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import AnalyticsOverviewResponse, RiskScoreResponse, TimeseriesResponse
from api.dependencies import (
    get_analytics_overview_payload,
    get_risk_score_payload,
    get_timeseries_payload,
)

__all__ = ["router"]

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_overview(
    overview: AnalyticsOverviewResponse = Depends(get_analytics_overview_payload),
) -> AnalyticsOverviewResponse:
    """Return dashboard-oriented analytics summary metrics."""
    return overview


@router.get("/risk-scores/{entity_id}", response_model=RiskScoreResponse)
async def get_risk_score(
    risk_score: RiskScoreResponse = Depends(get_risk_score_payload),
) -> RiskScoreResponse:
    """Return risk score details for one entity."""
    return risk_score


@router.get("/timeseries/{entity_id}", response_model=TimeseriesResponse)
async def get_timeseries(
    timeseries: TimeseriesResponse = Depends(get_timeseries_payload),
) -> TimeseriesResponse:
    """Return a timeseries payload for one entity."""
    return timeseries