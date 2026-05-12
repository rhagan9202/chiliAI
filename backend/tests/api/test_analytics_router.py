"""Tests for the analytics API router."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.models import ClusterSummary
from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service import create_gnn_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RankedRiskEntry
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.models import TimeSeriesObservation
from analytics.timeseries.protocols import TimeseriesServiceProtocol
from analytics.timeseries.service import create_timeseries_service
from api.routers.analytics import (
    get_gnn_service,
    get_risk_service,
    get_timeseries_service,
    router,
)
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


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_risk_service] = _build_risk_service
    app.dependency_overrides[get_timeseries_service] = _build_timeseries_service
    app.dependency_overrides[get_gnn_service] = lambda: _build_gnn_service(enabled=True)
    return TestClient(app)


def test_list_risk_scores_returns_ranked_items(client: TestClient) -> None:
    response = client.get("/analytics/risk-scores", params={"kb_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-1"
    assert payload["total"] == 3
    assert payload["items"][0]["entity_id"] == "provider-1"
    assert payload["items"][0]["overall_score"] == 0.91


def test_list_risk_scores_filters_by_entity_type(client: TestClient) -> None:
    response = client.get(
        "/analytics/risk-scores",
        params={"kb_id": "kb-1", "entity_type": "claim", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["entity_type"] == "claim"


def test_list_risk_scores_requires_kb_id(client: TestClient) -> None:
    response = client.get("/analytics/risk-scores")

    assert response.status_code == 422


def test_query_timeseries_returns_points_in_range(client: TestClient) -> None:
    response = client.get(
        "/analytics/timeseries",
        params={
            "kb_id": "kb-1",
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
        params={"kb_id": "kb-1", "metric": "claim_volume"},
    )

    assert response.status_code == 422


def test_query_timeseries_rejects_inverted_range(client: TestClient) -> None:
    response = client.get(
        "/analytics/timeseries",
        params={
            "kb_id": "kb-1",
            "metric": "claim_volume",
            "start": "2026-04-05T00:00:00+00:00",
            "end": "2026-04-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 422


def test_list_gnn_clusters_returns_clusters_when_enabled(client: TestClient) -> None:
    response = client.get("/analytics/gnn/clusters", params={"kb_id": "kb-1"})

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

    response = test_client.get("/analytics/gnn/clusters", params={"kb_id": "kb-1"})

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
        assert client.get("/analytics/risk-scores", params={"kb_id": "kb-demo"}).status_code == 401
        # Viewer cookie -> 200
        client.cookies.set("chiliai_session", "sid-viewer")
        assert client.get("/analytics/risk-scores", params={"kb_id": "kb-demo"}).status_code == 200
