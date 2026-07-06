"""Air Force housing dashboard API endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from api.contracts import (
    HousingInstallationsResponse,
    HousingOverviewResponse,
    HousingPortfolioSummaryResponse,
)
from api.middleware.rbac import require_role

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
) -> HousingOverviewResponse:
    """Return a safe empty executive housing KPI model."""
    return HousingOverviewResponse(
        period_start=period_start,
        period_end=period_end,
        portfolio_summary=HousingPortfolioSummaryResponse(),
        executive_kpis=[],
    )


@router.get(
    "/installations",
    response_model=HousingInstallationsResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_installations(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
) -> HousingInstallationsResponse:
    """Return a safe empty installation list and map model."""
    return HousingInstallationsResponse(
        period_start=period_start,
        period_end=period_end,
        total=0,
        items=[],
        map_points=[],
    )
