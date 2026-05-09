"""Tests for the alerts API router."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.alerts import get_alerts_service, router as alerts_router
from monitoring.adapters.in_memory import InMemoryAlertRepository
from monitoring.service import AlertsService, create_alerts_service
from shared.types import Alert


def _alert(
    *,
    alert_id: str,
    severity: str = "high",
    entity_type: str = "provider",
    status: str = "open",
    entity_id: str | None = None,
) -> Alert:
    return Alert(
        id=alert_id,
        entity_type=entity_type,
        entity_id=entity_id or f"{entity_type}-{alert_id}",
        severity=severity,
        title=f"Threshold exceeded for {alert_id}",
        reasoning="Score exceeded configured threshold.",
        evidence_pack_id=None,
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        status=status,  # pyright: ignore[reportArgumentType]
    )


def _build_client(alerts: list[Alert]) -> tuple[TestClient, AlertsService]:
    repository = InMemoryAlertRepository(alerts=alerts)
    service = create_alerts_service(repository)
    app = FastAPI()
    app.include_router(alerts_router)
    app.dependency_overrides[get_alerts_service] = lambda: service
    return TestClient(app), service


@pytest.fixture()
def seeded_alerts() -> list[Alert]:
    return [
        _alert(alert_id="a-1", severity="high", entity_type="provider", status="open"),
        _alert(alert_id="a-2", severity="medium", entity_type="provider", status="acknowledged"),
        _alert(alert_id="a-3", severity="high", entity_type="claim", status="resolved"),
        _alert(alert_id="a-4", severity="low", entity_type="claim", status="open"),
        _alert(alert_id="a-5", severity="high", entity_type="provider", status="open"),
    ]


class TestListAlerts:
    def test_returns_all_alerts_when_no_filters_supplied(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get("/alerts")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert [item["id"] for item in body["items"]] == [
            "a-1",
            "a-2",
            "a-3",
            "a-4",
            "a-5",
        ]

    def test_returns_empty_list_when_no_alerts_match(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get("/alerts", params={"severity": "critical"})

        assert response.status_code == 200
        body = response.json()
        assert body == {"items": [], "total": 0}

    def test_returns_empty_list_when_repository_is_empty(self) -> None:
        client, _ = _build_client([])

        response = client.get("/alerts")

        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}

    def test_filters_by_severity(self, seeded_alerts: list[Alert]) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get("/alerts", params={"severity": "high"})

        body = response.json()
        assert body["total"] == 3
        assert {item["id"] for item in body["items"]} == {"a-1", "a-3", "a-5"}

    def test_filters_by_entity_type(self, seeded_alerts: list[Alert]) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get("/alerts", params={"entity_type": "claim"})

        body = response.json()
        assert body["total"] == 2
        assert {item["id"] for item in body["items"]} == {"a-3", "a-4"}

    def test_filters_by_status(self, seeded_alerts: list[Alert]) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get("/alerts", params={"status": "open"})

        body = response.json()
        assert body["total"] == 3
        assert {item["id"] for item in body["items"]} == {"a-1", "a-4", "a-5"}

    def test_filters_compose(self, seeded_alerts: list[Alert]) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get(
            "/alerts",
            params={"severity": "high", "entity_type": "provider", "status": "open"},
        )

        body = response.json()
        assert body["total"] == 2
        assert {item["id"] for item in body["items"]} == {"a-1", "a-5"}

    def test_pagination_respects_limit_and_offset(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.get("/alerts", params={"limit": 2, "offset": 1})

        body = response.json()
        assert body["total"] == 5
        assert [item["id"] for item in body["items"]] == ["a-2", "a-3"]

    def test_invalid_limit_returns_422(self) -> None:
        client, _ = _build_client([])

        response = client.get("/alerts", params={"limit": 0})

        assert response.status_code == 422


class TestAcknowledgeAlert:
    def test_acknowledge_open_alert_returns_updated_record(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post("/alerts/a-1/acknowledge")

        assert response.status_code == 200
        payload = response.json()
        assert payload["alert"]["id"] == "a-1"
        assert payload["alert"]["status"] == "acknowledged"
        assert payload["alert"]["acknowledged"] is True
        assert payload["alert"]["updated_at"] is not None

    def test_acknowledge_unknown_alert_returns_404(self) -> None:
        client, _ = _build_client([])

        response = client.post("/alerts/missing/acknowledge")

        assert response.status_code == 404
        assert "missing" in response.json()["detail"]

    def test_acknowledge_resolved_alert_returns_409(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post("/alerts/a-3/acknowledge")

        assert response.status_code == 409


class TestResolveAlert:
    def test_resolve_open_alert_returns_updated_record(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post(
            "/alerts/a-1/resolve",
            json={"resolved_by": "analyst@example.com", "notes": "False positive."},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["alert"]["status"] == "resolved"
        assert payload["alert"]["resolved_by"] == "analyst@example.com"
        assert payload["alert"]["resolution_notes"] == "False positive."

    def test_resolve_acknowledged_alert_returns_updated_record(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post(
            "/alerts/a-2/resolve",
            json={"resolved_by": "analyst@example.com"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["alert"]["status"] == "resolved"
        assert payload["alert"]["resolution_notes"] is None

    def test_resolve_unknown_alert_returns_404(self) -> None:
        client, _ = _build_client([])

        response = client.post(
            "/alerts/missing/resolve",
            json={"resolved_by": "analyst@example.com"},
        )

        assert response.status_code == 404

    def test_resolve_already_resolved_alert_returns_409(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post(
            "/alerts/a-3/resolve",
            json={"resolved_by": "analyst@example.com"},
        )

        assert response.status_code == 409

    def test_resolve_requires_resolved_by(self, seeded_alerts: list[Alert]) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post("/alerts/a-1/resolve", json={})

        assert response.status_code == 422

    def test_resolve_rejects_blank_resolved_by(
        self, seeded_alerts: list[Alert]
    ) -> None:
        client, _ = _build_client(seeded_alerts)

        response = client.post("/alerts/a-1/resolve", json={"resolved_by": ""})

        assert response.status_code == 422


class TestDefaultDependencyFactory:
    def test_get_alerts_service_returns_protocol_compatible_singleton(self) -> None:
        get_alerts_service.cache_clear()
        try:
            service = get_alerts_service()
            again = get_alerts_service()
        finally:
            get_alerts_service.cache_clear()

        assert service is again
        assert isinstance(service, AlertsService)


def test_alerts_get_requires_viewer_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /alerts requires viewer role."""
    import time
    from pathlib import Path

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", lambda app: None)

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
        assert client.get("/alerts").status_code == 401
        # Viewer cookie -> 200
        client.cookies.set("chiliai_session", "sid-viewer")
        assert client.get("/alerts").status_code == 200


def test_alerts_acknowledge_requires_analyst_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /alerts/{id}/acknowledge requires analyst role."""
    import time
    from pathlib import Path

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", lambda app: None)

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
    store.save(
        SessionRecord(
            session_id="sid-analyst",
            user_id="u-analyst",
            roles=["analyst"],
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
        # Viewer cookie -> 403 (role denied before body executed)
        client.cookies.set("chiliai_session", "sid-viewer")
        assert client.post("/alerts/nonexistent-alert/acknowledge").status_code == 403
        # Analyst cookie -> 200 or 404 (role passes; alert may not exist)
        client.cookies.set("chiliai_session", "sid-analyst")
        result = client.post("/alerts/nonexistent-alert/acknowledge").status_code
        assert result in (200, 404)
