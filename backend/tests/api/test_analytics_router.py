"""Tests for the analytics API router."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.models import ClusterSummary
from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service import create_gnn_service
from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.models import EntityMetricSample
from analytics.peerstats.adapters.in_memory import InMemoryDerivedRiskSignalWriter
from analytics.peerstats.exceptions import PeerStatsSourceError
from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate
from analytics.peerstats.peer_analysis import PeerAnalysisService
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RankedRiskEntry, RiskProfile, RiskSignal
from analytics.risk.projection_service import RiskProjectionService
from analytics.risk.projections import InMemoryRiskProjectionRepository, RiskProjectionRow
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from analytics.timeseries.adapters.in_memory import (
    InMemoryTimeSeriesHistorySource,
    InMemoryTimeseriesAnomalyStore,
)
from analytics.timeseries.adapters.postgres import PostgresTimeSeriesHistorySource
from analytics.timeseries.adapters.record_aggregates import RecordAggregateTimeSeriesSource
from analytics.timeseries.models import TimeSeriesObservation, TimeseriesAnomalyRecord
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import create_timeseries_service
from api.contracts import (
    AnalyticsOverviewResponse,
    EntityTimeseriesResponse,
    RiskProjectionRebuildRequest,
    RiskScoreResponse,
)
from api.dependencies import (
    get_analytics_overview_payload,
    get_entity_series_source,
    get_gnn_service,
    get_peer_analysis_service,
    get_risk_projection_repository,
    get_risk_projection_service,
    get_risk_score_payload,
    get_risk_service,
    get_timeseries_anomaly_store,
    get_timeseries_payload,
    get_timeseries_service,
)
from api.routers import analytics as analytics_router
from api.routers.analytics import router
from config.schema import DatabaseConfig, TimeseriesMetricSpec
from database.runtime import create_connection_provider
from events.adapters.in_memory import InMemoryEventBus


def _build_risk_service() -> RiskServiceProtocol:
    return create_risk_service(
        InMemoryRiskSignalSource(
            ranked_entries=[
                RankedRiskEntry(
                    knowledge_base_id="kb-1",
                    entity_id="provider-1",
                    entity_type="provider",
                    overall_score=0.91,
                    risk_level="high",
                ),
                RankedRiskEntry(
                    knowledge_base_id="kb-1",
                    entity_id="provider-2",
                    entity_type="provider",
                    overall_score=0.6,
                    risk_level="medium",
                ),
                RankedRiskEntry(
                    knowledge_base_id="kb-1",
                    entity_id="claim-3",
                    entity_type="claim",
                    overall_score=0.45,
                    risk_level="low",
                ),
            ]
        ),
        event_bus=InMemoryEventBus(),
    )


def _build_timeseries_service() -> TimeseriesServiceProtocol:
    source = InMemoryTimeSeriesHistorySource()
    source.put_metric_observations(
        knowledge_base_id="kb-1",
        metric_name="claim_volume",
        observations=[
            TimeSeriesObservation(
                observed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                value=10.0,
            ),
            TimeSeriesObservation(
                observed_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                value=12.5,
            ),
            TimeSeriesObservation(
                observed_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
                value=20.0,
            ),
        ],
    )
    return create_timeseries_service(source, event_bus=InMemoryEventBus())


def _build_gnn_service(*, enabled: bool, with_clusters: bool = True) -> GnnServiceProtocol:
    snapshot_source = InMemoryGraphSnapshotSource()
    if with_clusters:
        snapshot_source.put_clusters(
            "kb-1",
            [
                ClusterSummary(
                    cluster_id="cluster-1",
                    entity_ids=["provider-1", "provider-2"],
                    anomaly_score=0.84,
                    label="dense referrals",
                ),
                ClusterSummary(
                    cluster_id="cluster-2",
                    entity_ids=["claim-3"],
                    anomaly_score=0.12,
                    label=None,
                ),
            ],
        )
    return create_gnn_service(
        snapshot_source,
        event_bus=InMemoryEventBus(),
        gnn_enabled=lambda: enabled,
    )


def _build_projection_repository() -> InMemoryRiskProjectionRepository:
    return InMemoryRiskProjectionRepository(
        [
            RiskProjectionRow(
                knowledge_base_id="kb-1",
                entity_id="provider-1",
                entity_type="provider",
                overall_score=0.91,
                risk_level="high",
                top_typology_ids=["upcoding"],
                alert_ids=["alert-1"],
                case_ids=["case-1"],
                evidence_pack_ids=["evidence-1"],
                score_run_id="score-run-1",
                model_version="risk-linear-v1",
                catalog_version="cms-fraud-features-v1",
                scored_at=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 3, 10, 1, tzinfo=timezone.utc),
                status="case_open",
            ),
            RiskProjectionRow(
                knowledge_base_id="kb-1",
                entity_id="provider-2",
                entity_type="provider",
                overall_score=0.67,
                risk_level="medium",
                top_typology_ids=["billing-volume"],
                model_version="risk-linear-v1",
                catalog_version="cms-fraud-features-v1",
                scored_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 1, 10, 1, tzinfo=timezone.utc),
                status="active",
            ),
            RiskProjectionRow(
                knowledge_base_id="kb-1",
                entity_id="claim-1",
                entity_type="claim",
                overall_score=0.41,
                risk_level="low",
                top_typology_ids=["duplicate-claim"],
                model_version="risk-linear-v1",
                catalog_version="cms-fraud-features-v1",
                scored_at=datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 8, 3, 8, 1, tzinfo=timezone.utc),
                status="active",
            ),
        ]
    )


def _build_peer_analysis_service() -> PeerAnalysisService:
    writer = InMemoryDerivedRiskSignalWriter()
    interval = datetime(2026, 1, 12, tzinfo=timezone.utc)
    for entity_id, value in (
        ("provider:target", 100.0),
        ("provider:a", 10.0),
        ("provider:b", 50.0),
        ("provider:c", 75.0),
    ):
        writer.write_signals(
            [
                DerivedRiskSignal(
                    knowledge_base_id="kb-1",
                    entity_id=entity_id,
                    entity_type="provider",
                    metric_name="weekly_billing",
                    interval_start=interval,
                    peer_group_key="provider|cardiology",
                    aggregate_value=value,
                    peer_mean=50.0,
                    peer_std=20.0,
                    z_score=(value - 50.0) / 20.0,
                    signal_value=min(max(value / 100.0, 0.0), 1.0),
                    weight=1.0,
                    rationale="weekly billing compared to specialty peers",
                    correlation_id="corr-1",
                )
            ]
        )
    return PeerAnalysisService(writer, min_cohort_size=4)


class _StaticRiskProjectionRebuildSource:
    def __init__(self, rows: list[RiskProjectionRow]) -> None:
        self._rows = rows

    def load_projection_rows(self, knowledge_base_id: str) -> list[RiskProjectionRow]:
        return [
            row.model_copy(deep=True)
            for row in self._rows
            if row.knowledge_base_id == knowledge_base_id
        ]


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    projection_repository = _build_projection_repository()
    app.dependency_overrides[get_risk_service] = _build_risk_service
    app.dependency_overrides[get_risk_projection_repository] = lambda: projection_repository
    app.dependency_overrides[get_risk_projection_service] = lambda: RiskProjectionService(
        projection_repository
    )
    app.dependency_overrides[get_timeseries_service] = _build_timeseries_service
    app.dependency_overrides[get_gnn_service] = lambda: _build_gnn_service(enabled=True)
    app.dependency_overrides[get_peer_analysis_service] = _build_peer_analysis_service
    return TestClient(app)


def test_list_risk_scores_returns_ranked_items(client: TestClient) -> None:
    response = client.get("/analytics/risk-scores", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-1"
    assert payload["total"] == 3
    assert payload["items"][0]["entity_id"] == "provider-1"
    assert payload["items"][0]["overall_score"] == 0.91


def test_list_risk_scores_filters_by_entity_type(client: TestClient) -> None:
    response = client.get(
        "/analytics/risk-scores",
        params={"knowledge_base_id": "kb-1", "entity_type": "claim", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["entity_type"] == "claim"


def test_list_risk_scores_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/risk-scores")

    assert response.status_code == 422


def test_list_risk_projections_returns_projection_metadata() -> None:
    payload = analytics_router.list_risk_projections(
        kb_id="kb-1",
        entity_type=None,
        risk_level=None,
        typology_id=None,
        status=None,
        max_score_age_hours=None,
        as_of=None,
        limit=2,
        offset=0,
        repository=_build_projection_repository(),
    )

    assert payload.knowledge_base_id == "kb-1"
    assert payload.total == 3
    assert payload.limit == 2
    assert payload.offset == 0
    first = payload.items[0]
    assert first.entity_id == "provider-1"
    assert first.top_typology_ids == ["upcoding"]
    assert first.alert_ids == ["alert-1"]
    assert first.case_ids == ["case-1"]
    assert first.evidence_pack_ids == ["evidence-1"]
    assert first.score_run_id == "score-run-1"
    assert first.model_version == "risk-linear-v1"
    assert first.catalog_version == "cms-fraud-features-v1"
    assert first.status == "case_open"


def test_list_risk_projections_filters_score_age_independently() -> None:
    payload = analytics_router.list_risk_projections(
        kb_id="kb-1",
        entity_type=None,
        risk_level=None,
        typology_id=None,
        status=None,
        max_score_age_hours=24,
        as_of=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        limit=20,
        offset=0,
        repository=_build_projection_repository(),
    )

    assert payload.total == 2
    assert [item.entity_id for item in payload.items] == ["provider-1", "claim-1"]


def test_list_risk_projections_filters_operator_facets() -> None:
    payload = analytics_router.list_risk_projections(
        kb_id="kb-1",
        entity_type="provider",
        risk_level="high",
        typology_id="upcoding",
        status="case_open",
        max_score_age_hours=24,
        as_of=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        limit=20,
        offset=0,
        repository=_build_projection_repository(),
    )

    assert payload.total == 1
    assert payload.items[0].entity_id == "provider-1"


def test_list_risk_projections_supports_offset_pagination() -> None:
    payload = analytics_router.list_risk_projections(
        kb_id="kb-1",
        entity_type=None,
        risk_level=None,
        typology_id=None,
        status=None,
        max_score_age_hours=None,
        as_of=None,
        limit=1,
        offset=1,
        repository=_build_projection_repository(),
    )

    assert payload.total == 3
    assert payload.items[0].entity_id == "provider-2"


def test_list_risk_projections_openapi_declares_query_contract() -> None:
    app = FastAPI()
    app.include_router(router)

    operation = app.openapi()["paths"]["/analytics/risk-projections"]["get"]
    parameters = {param["name"]: param for param in operation["parameters"]}
    assert parameters["knowledge_base_id"]["required"] is True
    assert parameters["knowledge_base_id"]["in"] == "query"
    assert parameters["risk_level"]["schema"]["anyOf"][0]["enum"] == [
        "low",
        "medium",
        "high",
        "critical",
    ]
    assert parameters["status"]["schema"]["anyOf"][0]["enum"] == [
        "active",
        "case_open",
        "resolved",
        "suppressed",
        "stale",
    ]
    assert parameters["limit"]["schema"]["exclusiveMinimum"] == 0
    assert parameters["limit"]["schema"]["maximum"] == 500
    assert parameters["offset"]["schema"]["minimum"] == 0
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RiskProjectionListResponse"
    )


def test_get_peer_analysis_returns_cohort_context(client: TestClient) -> None:
    response = client.get(
        "/analytics/peer-analysis/provider:target",
        params={"knowledge_base_id": "kb-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-1"
    assert payload["entity_id"] == "provider:target"
    assert payload["metrics"][0]["metric_name"] == "weekly_billing"
    assert payload["metrics"][0]["entity_value"] == 100.0
    assert payload["metrics"][0]["peer_mean"] == 50.0
    assert payload["metrics"][0]["peer_std"] == 20.0
    assert payload["metrics"][0]["z_score"] == 2.5
    assert payload["metrics"][0]["cohort_size"] == 4
    assert payload["metrics"][0]["percentile"] == 100.0
    assert payload["metrics"][0]["confidence"] == "normal"


def test_get_peer_analysis_filters_metric(client: TestClient) -> None:
    response = client.get(
        "/analytics/peer-analysis/provider:target",
        params={"knowledge_base_id": "kb-1", "metric": "missing_metric"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"] == []


def test_peer_analysis_openapi_declares_query_contract_and_role_guard() -> None:
    app = FastAPI()
    app.include_router(router)

    operation = app.openapi()["paths"]["/analytics/peer-analysis/{entity_id}"]["get"]
    parameters = {param["name"]: param for param in operation["parameters"]}
    assert parameters["knowledge_base_id"]["required"] is True
    assert parameters["metric"]["required"] is False
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/PeerAnalysisResponse"
    )

    roles_by_path: dict[str, set[str]] = {}
    for route_obj in router.routes:
        path = getattr(route_obj, "path", "")
        roles: set[str] = set()
        for dependency in getattr(route_obj, "dependencies", []):
            required = getattr(dependency.dependency, "_chiliai_required_role", None)
            if isinstance(required, str):
                roles.add(required)
        roles_by_path[path] = roles

    assert roles_by_path["/analytics/peer-analysis/{entity_id}"] == {"viewer"}


def test_list_risk_projections_rejects_naive_as_of() -> None:
    with pytest.raises(HTTPException) as exc_info:
        analytics_router._projection_as_of(datetime(2026, 8, 3, 12, 0))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "as_of must include timezone information."


def test_rebuild_risk_projections_exposes_operator_seam() -> None:
    repository = _build_projection_repository()
    source = _StaticRiskProjectionRebuildSource(repository.list_all("kb-1"))
    payload = analytics_router.rebuild_risk_projections(
        RiskProjectionRebuildRequest(knowledge_base_id="kb-1"),
        source,
        RiskProjectionService(repository),
    )

    assert payload.knowledge_base_id == "kb-1"
    assert payload.changed is False
    assert payload.deleted == 0
    assert payload.upserted == 0
    assert payload.status == "completed"


def test_rebuild_risk_projections_fails_when_source_unconfigured() -> None:
    repository = _build_projection_repository()
    with pytest.raises(HTTPException) as exc_info:
        analytics_router.rebuild_risk_projections(
            RiskProjectionRebuildRequest(knowledge_base_id="kb-1"),
            None,
            RiskProjectionService(repository),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Risk projection rebuild source is not configured."


def test_rebuild_risk_projections_uses_configured_source() -> None:
    repository = _build_projection_repository()
    source = _StaticRiskProjectionRebuildSource(repository.list_all("kb-1")[:1])

    payload = analytics_router.rebuild_risk_projections(
        RiskProjectionRebuildRequest(knowledge_base_id="kb-1"),
        source,
        RiskProjectionService(repository),
    )

    assert payload.knowledge_base_id == "kb-1"
    assert payload.changed is True
    assert payload.deleted == 3
    assert payload.upserted == 1
    assert payload.status == "completed"
    assert [row.entity_id for row in repository.list_all("kb-1")] == ["provider-1"]


def test_rebuild_risk_projections_openapi_declares_body_and_response_contract() -> None:
    app = FastAPI()
    app.include_router(router)

    operation = app.openapi()["paths"]["/analytics/risk-projections/rebuild"]["post"]
    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RiskProjectionRebuildRequest"
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RiskProjectionRebuildResponse"
    )


def test_risk_projection_routes_declare_role_guards() -> None:
    roles_by_path: dict[str, set[str]] = {}
    for route_obj in router.routes:
        path = getattr(route_obj, "path", "")
        roles: set[str] = set()
        for dependency in getattr(route_obj, "dependencies", []):
            required = getattr(dependency.dependency, "_chiliai_required_role", None)
            if isinstance(required, str):
                roles.add(required)
        roles_by_path[path] = roles

    assert roles_by_path["/analytics/risk-projections"] == {"viewer"}
    assert roles_by_path["/analytics/risk-projections/rebuild"] == {"analyst"}


def test_detail_risk_score_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/risk-scores/provider-1")

    assert response.status_code == 422


def test_detail_risk_score_is_kb_scoped() -> None:
    app = FastAPI()
    app.include_router(router)

    def risk_payload(
        entity_id: str,
        kb_id: str = Query(..., alias="knowledge_base_id"),
    ) -> RiskScoreResponse:
        assert entity_id == "provider-1"
        assert kb_id == "kb-live"
        return RiskScoreResponse(
            entity_id=entity_id,
            overall_score=0.0,
            risk_level="low",
            factors=[],
            availability_status="unavailable",
            unavailable_reason="No risk profile has been generated for this entity.",
        )

    app.dependency_overrides[get_risk_score_payload] = risk_payload
    test_client = TestClient(app)

    response = test_client.get(
        "/analytics/risk-scores/provider-1",
        params={"knowledge_base_id": "kb-live"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-1"
    assert payload["availability_status"] == "unavailable"


def test_detail_risk_score_served_from_di_risk_service() -> None:
    """B2 moved the risk detail route off ApiState's seeded profiles onto the
    DI risk service, so live derived signals (peerstats + timeseries anomaly
    families) reach the factor breakdown for real knowledge bases.
    """
    app = FastAPI()
    app.include_router(router)

    service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-live",
                    entity_id="provider-1",
                    signals=[
                        RiskSignal(
                            signal_name="peer_group_deviation",
                            value=0.8,
                            weight=1.0,
                        ),
                        RiskSignal(
                            signal_name="timeseries_anomaly:weekly_carrier_billing_self",
                            value=0.6,
                            weight=1.0,
                        ),
                    ],
                )
            ]
        ),
        event_bus=InMemoryEventBus(),
    )
    app.dependency_overrides[get_risk_service] = lambda: service
    test_client = TestClient(app)

    risk_response = test_client.get(
        "/analytics/risk-scores/provider-1",
        params={"knowledge_base_id": "kb-live"},
    )

    assert risk_response.status_code == 200
    payload = risk_response.json()
    assert payload["entity_id"] == "provider-1"
    assert payload["availability_status"] == "available"
    assert payload["overall_score"] > 0.0
    factor_names = {factor["factor_name"] for factor in payload["factors"]}
    assert factor_names == {
        "peer_group_deviation",
        "timeseries_anomaly:weekly_carrier_billing_self",
    }


def test_detail_risk_score_unavailable_without_registered_signals() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_risk_service] = lambda: create_risk_service(
        InMemoryRiskSignalSource(),
        event_bus=InMemoryEventBus(),
    )
    test_client = TestClient(app)

    risk_response = test_client.get(
        "/analytics/risk-scores/provider-1",
        params={"knowledge_base_id": "kb-live"},
    )

    assert risk_response.status_code == 200
    payload = risk_response.json()
    assert payload["availability_status"] == "unavailable"
    assert payload["factors"] == []


def test_unexpected_risk_errors_are_not_converted_to_unavailable() -> None:
    app = FastAPI()
    app.include_router(router)

    class BrokenRiskService:
        def assess(self, request: object) -> RiskScoreResponse:
            del request
            raise RuntimeError("risk backend unavailable")

    app.dependency_overrides[get_risk_service] = BrokenRiskService
    test_client = TestClient(app)

    with pytest.raises(RuntimeError, match="risk backend unavailable"):
        test_client.get(
            "/analytics/risk-scores/provider-1",
            params={"knowledge_base_id": "kb-live"},
        )


def test_query_timeseries_returns_points_in_range(client: TestClient) -> None:
    response = client.get(
        "/analytics/timeseries",
        params={
            "knowledge_base_id": "kb-1",
            "metric": "claim_volume",
            "start": "2026-04-01T00:00:00+00:00",
            "end": "2026-04-03T00:00:00+00:00",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_name"] == "claim_volume"
    assert len(payload["points"]) == 2
    assert payload["points"][0]["value"] == 10.0


def test_query_timeseries_requires_required_params(client: TestClient) -> None:
    response = client.get(
        "/analytics/timeseries",
        params={"knowledge_base_id": "kb-1", "metric": "claim_volume"},
    )

    assert response.status_code == 422


def test_query_timeseries_rejects_inverted_range(client: TestClient) -> None:
    response = client.get(
        "/analytics/timeseries",
        params={
            "knowledge_base_id": "kb-1",
            "metric": "claim_volume",
            "start": "2026-04-05T00:00:00+00:00",
            "end": "2026-04-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_query_timeseries_returns_seeded_postgres_rows() -> None:
    """Request-level proof that GET /analytics/timeseries reads real rows
    through PostgresTimeSeriesHistorySource, not just the in-memory adapter
    (analytics.07 AC — the graph-scope range route's Postgres wiring)."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not set; skipping Postgres timeseries route test.")

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresEntityMetricRepository(provider)
    kb_id = "kb-ts-router-integration"
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history WHERE knowledge_base_id = %s",
                (kb_id,),
            )
            conn.execute(
                "DELETE FROM entity_metrics_current WHERE knowledge_base_id = %s",
                (kb_id,),
            )
            conn.commit()

        repo.record_metrics(
            [
                EntityMetricSample(
                    knowledge_base_id=kb_id,
                    entity_id="__graph__",
                    metric_name="entity_count",
                    value=float(index) * 5.0,
                    observed_at=base + timedelta(minutes=index),
                    correlation_id=f"corr-{index}",
                )
                for index in range(3)
            ]
        )

        source = PostgresTimeSeriesHistorySource(provider)
        service = create_timeseries_service(source, event_bus=InMemoryEventBus())

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_timeseries_service] = lambda: service
        test_client = TestClient(app)

        response = test_client.get(
            "/analytics/timeseries",
            params={
                "knowledge_base_id": kb_id,
                "metric": "entity_count",
                "start": base.isoformat(),
                "end": (base + timedelta(minutes=2)).isoformat(),
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["metric_name"] == "entity_count"
        assert [point["value"] for point in payload["points"]] == [0.0, 5.0, 10.0]
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM entity_metric_history WHERE knowledge_base_id = %s",
                (kb_id,),
            )
            conn.execute(
                "DELETE FROM entity_metrics_current WHERE knowledge_base_id = %s",
                (kb_id,),
            )
            conn.commit()
        provider.close()


def test_detail_timeseries_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/timeseries/provider-1")

    assert response.status_code == 422


def test_detail_timeseries_is_kb_scoped() -> None:
    app = FastAPI()
    app.include_router(router)

    def timeseries_payload(
        entity_id: str,
        kb_id: str = Query(..., alias="knowledge_base_id"),
    ) -> EntityTimeseriesResponse:
        assert entity_id == "provider-1"
        assert kb_id == "kb-live"
        return EntityTimeseriesResponse(
            entity_id=entity_id,
            metric_name="normalized_alert_pressure",
            points=[],
            availability_status="unavailable",
            unavailable_reason="No time series has been generated for this entity.",
        )

    app.dependency_overrides[get_timeseries_payload] = timeseries_payload
    test_client = TestClient(app)

    response = test_client.get(
        "/analytics/timeseries/provider-1",
        params={"knowledge_base_id": "kb-live"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-1"
    assert payload["availability_status"] == "unavailable"


def _timeseries_metric_spec() -> TimeseriesMetricSpec:
    return TimeseriesMetricSpec(
        name="weekly_billing_self",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="npi",
        value_column="amount",
        aggregation="sum",
        interval="week",
        time_column="service_date",
    )


class _FakeColumnSource:
    """Protocol double returning canned aggregates (Task 3's test double shape)."""

    def __init__(self, aggregates: list[PeerAggregate]) -> None:
        self._aggregates = aggregates

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: object,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        del knowledge_base_id, spec, interval_starts
        return self._aggregates


def test_entity_timeseries_serves_series_with_persisted_anomalies() -> None:
    spec = _timeseries_metric_spec()
    bucket_1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bucket_2 = datetime(2026, 1, 8, tzinfo=timezone.utc)
    bucket_3 = datetime(2026, 1, 15, tzinfo=timezone.utc)
    column_source = _FakeColumnSource(
        [
            PeerAggregate(
                entity_id="provider:1",
                entity_type="provider",
                peer_group_key="provider",
                interval_start=bucket_1,
                aggregate_value=100.0,
            ),
            PeerAggregate(
                entity_id="provider:1",
                entity_type="provider",
                peer_group_key="provider",
                interval_start=bucket_2,
                aggregate_value=150.0,
            ),
            PeerAggregate(
                entity_id="provider:1",
                entity_type="provider",
                peer_group_key="provider",
                interval_start=bucket_3,
                aggregate_value=400.0,
            ),
        ]
    )
    source = RecordAggregateTimeSeriesSource(column_source, specs=[spec])

    anomaly_store = InMemoryTimeseriesAnomalyStore()
    anomaly_store.write_anomalies(
        [
            TimeseriesAnomalyRecord(
                knowledge_base_id="kb-1",
                entity_id="provider:1",
                metric_name=spec.name,
                observed_at=bucket_3,
                observed_value=400.0,
                expected_value=125.0,
                z_score=3.1,
                severity=0.9,
                detection_strategy="z_score",
                correlation_id="corr-1",
            )
        ]
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_entity_series_source] = lambda: source
    app.dependency_overrides[get_timeseries_anomaly_store] = lambda: anomaly_store
    test_client = TestClient(app)

    response = test_client.get("/analytics/timeseries/provider:1", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_name"] == spec.name
    assert len(payload["points"]) == 3
    assert [point["is_anomaly"] for point in payload["points"]] == [False, False, True]
    assert payload["availability_status"] == "available"


def test_entity_timeseries_unavailable_when_no_spec_has_data() -> None:
    spec = _timeseries_metric_spec()
    source = RecordAggregateTimeSeriesSource(_FakeColumnSource([]), specs=[spec])
    anomaly_store = InMemoryTimeseriesAnomalyStore()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_entity_series_source] = lambda: source
    app.dependency_overrides[get_timeseries_anomaly_store] = lambda: anomaly_store
    test_client = TestClient(app)

    response = test_client.get("/analytics/timeseries/provider:1", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["availability_status"] == "unavailable"
    assert payload["points"] == []
    assert payload["unavailable_reason"] is not None


def test_entity_timeseries_infra_error_propagates_instead_of_unavailable() -> None:
    """Infra errors from the column source propagate; only a no-data ValueError
    from ``load_series`` falls through to the next spec. A broken backing store
    must not be swallowed into a 200 ``unavailable`` response."""
    spec = _timeseries_metric_spec()

    class _BrokenColumnSource:
        def load_interval_aggregates(
            self,
            *,
            knowledge_base_id: str,
            spec: object,
            interval_starts: list[datetime],
        ) -> list[PeerAggregate]:
            del knowledge_base_id, spec, interval_starts
            raise PeerStatsSourceError("record aggregation backend unavailable")

    source = RecordAggregateTimeSeriesSource(_BrokenColumnSource(), specs=[spec])
    anomaly_store = InMemoryTimeseriesAnomalyStore()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_entity_series_source] = lambda: source
    app.dependency_overrides[get_timeseries_anomaly_store] = lambda: anomaly_store
    test_client = TestClient(app)

    with pytest.raises(PeerStatsSourceError, match="record aggregation backend unavailable"):
        test_client.get("/analytics/timeseries/provider:1", params={"knowledge_base_id": "kb-1"})


def test_list_gnn_clusters_returns_clusters_when_enabled(client: TestClient) -> None:
    response = client.get("/analytics/gnn/clusters", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-1"
    assert len(payload["clusters"]) == 2
    first = payload["clusters"][0]
    assert first["cluster_id"] == "cluster-1"
    assert first["entity_ids"] == ["provider-1", "provider-2"]
    assert first["anomaly_score"] == 0.84
    assert first["label"] == "dense referrals"


def test_list_gnn_clusters_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/gnn/clusters")

    assert response.status_code == 422


def test_list_gnn_clusters_returns_empty_when_disabled() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_gnn_service] = lambda: _build_gnn_service(enabled=False)
    test_client = TestClient(app)

    response = test_client.get("/analytics/gnn/clusters", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-1"
    assert payload["clusters"] == []


def test_default_di_factories_return_runtime_checkable_protocols() -> None:
    risk_service = get_risk_service()
    timeseries_service = get_timeseries_service()
    gnn_service = get_gnn_service()

    assert isinstance(risk_service, RiskServiceProtocol)
    assert isinstance(timeseries_service, TimeseriesServiceProtocol)
    assert isinstance(gnn_service, GnnServiceProtocol)


def test_overview_payload_can_be_overridden_from_live_projection() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_analytics_overview_payload] = lambda: AnalyticsOverviewResponse(
        active_alerts=0,
        open_cases=0,
        entities_monitored=4,
        high_risk_entities=0,
    )
    test_client = TestClient(app)

    response = test_client.get("/analytics/overview")

    assert response.status_code == 200
    assert response.json() == {
        "active_alerts": 0,
        "open_cases": 0,
        "entities_monitored": 4,
        "high_risk_entities": 0,
    }


def test_default_router_returns_empty_results_with_no_seed_data() -> None:
    """Without dependency_overrides, the router resolves its services
    through api/dependencies — which returns empty in-memory sources.

    Regression guard against the previous behavior where the router's
    local @lru_cache `_stub_*` factories pre-seeded Medicare fixture data
    (kb-demo / provider-1 / claim-9). Production endpoints must not
    surface that domain-specific demo data; they must return empty when
    nothing has been written for the active domain.
    """
    import api.dependencies as dependencies

    # The DI lru_caches may be populated from earlier tests — clear them
    # so we observe a truly empty default for this assertion.
    dependencies.get_risk_service.cache_clear()
    dependencies.get_timeseries_service.cache_clear()
    dependencies.get_gnn_service.cache_clear()
    dependencies.get_risk_signal_source.cache_clear()
    dependencies.get_timeseries_history_source.cache_clear()
    dependencies.get_graph_snapshot_source.cache_clear()

    app = FastAPI()
    app.include_router(router)
    test_client = TestClient(app)

    risk_response = test_client.get(
        "/analytics/risk-scores", params={"knowledge_base_id": "kb-demo"}
    )
    assert risk_response.status_code == 200
    risk_payload = risk_response.json()
    assert risk_payload["knowledge_base_id"] == "kb-demo"
    assert risk_payload["items"] == []
    assert risk_payload["total"] == 0

    gnn_response = test_client.get(
        "/analytics/gnn/clusters", params={"knowledge_base_id": "kb-demo"}
    )
    assert gnn_response.status_code == 200
    gnn_payload = gnn_response.json()
    assert gnn_payload["clusters"] == []


def test_analytics_risk_scores_requires_viewer_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /analytics/risk-scores requires viewer role when auth is enabled."""
    import time
    from pathlib import Path

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    def _skip_complete_check(app: FastAPI) -> None:
        """Bypass route completeness checks for this focused auth test."""

        del app

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", _skip_complete_check)

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    domain = load_config(MEDICARE_YAML).model_copy(update={"auth": auth_cfg})
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-viewer",
            user_id="u-viewer",
            roles=["viewer"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # No cookie -> 401
        assert client.get("/analytics/risk-scores", params={"knowledge_base_id": "kb-demo"}).status_code == 401
        # Viewer cookie -> 200
        client.cookies.set("chiliai_session", "sid-viewer")
        assert client.get("/analytics/risk-scores", params={"knowledge_base_id": "kb-demo"}).status_code == 200
