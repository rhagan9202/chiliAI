"""Analytics API endpoints for risk scores, timeseries, and GNN clusters."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service import create_gnn_service
from analytics.gnn.service_models import GnnClusterRequest, GnnClusterResponse
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RankedRiskEntry
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskScoreListRequest, RiskScoreListResponse
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.models import TimeSeriesObservation
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import TimeseriesQueryRequest, TimeseriesResponse
from events.adapters.in_memory import InMemoryEventBus

__all__ = ["router"]


@lru_cache(maxsize=1)
def _stub_event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@lru_cache(maxsize=1)
def _stub_risk_signal_source() -> InMemoryRiskSignalSource:
    return InMemoryRiskSignalSource(
        ranked_entries=[
            RankedRiskEntry(
                knowledge_base_id="kb-demo",
                entity_id="provider-1",
                entity_type="provider",
                overall_score=0.92,
                risk_level="high",
            ),
            RankedRiskEntry(
                knowledge_base_id="kb-demo",
                entity_id="provider-2",
                entity_type="provider",
                overall_score=0.71,
                risk_level="medium",
            ),
            RankedRiskEntry(
                knowledge_base_id="kb-demo",
                entity_id="claim-9",
                entity_type="claim",
                overall_score=0.55,
                risk_level="medium",
            ),
        ]
    )


@lru_cache(maxsize=1)
def _stub_timeseries_history_source() -> InMemoryTimeSeriesHistorySource:
    source = InMemoryTimeSeriesHistorySource()
    source.put_metric_observations(
        knowledge_base_id="kb-demo",
        metric_name="claim_volume",
        observations=[
            TimeSeriesObservation(observed_at=datetime.fromisoformat("2026-04-01T00:00:00+00:00"), value=10.0),
            TimeSeriesObservation(observed_at=datetime.fromisoformat("2026-04-02T00:00:00+00:00"), value=12.0),
            TimeSeriesObservation(observed_at=datetime.fromisoformat("2026-04-03T00:00:00+00:00"), value=11.0),
        ],
    )
    return source


@lru_cache(maxsize=1)
def _stub_graph_snapshot_source() -> InMemoryGraphSnapshotSource:
    return InMemoryGraphSnapshotSource()


def _gnn_disabled() -> bool:
    return False


def get_risk_service() -> RiskServiceProtocol:
    """Return the in-memory stub risk service used by the analytics router."""
    return create_risk_service(_stub_risk_signal_source(), event_bus=_stub_event_bus())


def get_timeseries_service() -> TimeseriesServiceProtocol:
    """Return the in-memory stub timeseries service used by the analytics router."""
    return create_timeseries_service(_stub_timeseries_history_source(), event_bus=_stub_event_bus())


def get_gnn_service() -> GnnServiceProtocol:
    """Return the in-memory stub GNN service used by the analytics router.

    The default stub reports GNN as disabled to honor the capability flag from
    `DomainConfig.capabilities.gnn`. Tests override this dependency directly to
    exercise enabled/disabled paths.
    """
    return create_gnn_service(
        _stub_graph_snapshot_source(),
        event_bus=_stub_event_bus(),
        gnn_enabled=_gnn_disabled,
    )


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/risk-scores", response_model=RiskScoreListResponse)
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


@router.get("/timeseries", response_model=TimeseriesResponse)
def query_timeseries(
    kb_id: str = Query(..., min_length=1),
    metric: str = Query(..., min_length=1),
    start: datetime = Query(...),
    end: datetime = Query(...),
    timeseries_service: TimeseriesServiceProtocol = Depends(get_timeseries_service),
) -> TimeseriesResponse:
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


@router.get("/gnn/clusters", response_model=GnnClusterResponse)
def list_gnn_clusters(
    kb_id: str = Query(..., min_length=1),
    gnn_service: GnnServiceProtocol = Depends(get_gnn_service),
) -> GnnClusterResponse:
    """Return GNN-derived clusters for a knowledge base.

    Returns an empty list when the GNN capability is disabled in config.
    """
    return gnn_service.list_clusters(GnnClusterRequest(knowledge_base_id=kb_id))
