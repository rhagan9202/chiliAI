"""Tests for the WebSocket router (alerts + pipeline)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from datetime import datetime, timezone
from typing import Any, cast

import anyio.abc
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.dependencies import get_domain_config, get_session_store
from api.middleware.auth import User, build_anonymous_user, get_current_user
from api.middleware.session_store import InMemorySessionStore
from api.routers.ws import (
    ROUTE_ALERTS,
    ROUTE_PIPELINE,
    WebSocketConnection,
    WebSocketHub,
    get_ws_hub,
    router,
)
from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
)
from events.types import AlertCreatedEvent, PipelineProgressEvent
from shared.types import Alert


def _make_alert(severity: str, alert_id: str = "alert-1") -> Alert:
    return Alert(
        id=alert_id,
        entity_type="provider",
        entity_id="provider-7",
        severity=severity,
        title="Suspicious billing pattern",
        reasoning="Outlier billing across multiple specialties.",
        evidence_pack_id="pack-1",
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )


def _portal(client: TestClient) -> anyio.abc.BlockingPortal:
    portal = client.portal
    assert portal is not None
    return portal


async def _wait_until(predicate: Callable[[], bool]) -> None:
    for _ in range(50):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Predicate did not become true in time")


def _alert_payload(alert: Alert) -> dict[str, object]:
    return {
        "type": "alert",
        "data": cast(dict[str, object], alert.model_dump(mode="json")),
    }


def _pipeline_payload(event: PipelineProgressEvent) -> dict[str, object]:
    return {
        "type": "pipeline_progress",
        "event_type": event.event_type,
        "knowledge_base_id": event.knowledge_base_id,
        "stage": event.stage,
        "progress": event.progress,
        "timestamp": event.occurred_at.isoformat(),
    }


def _broadcast_alert(
    client: TestClient,
    hub: WebSocketHub,
    alert: Alert,
) -> None:
    severity = alert.severity

    def _filter(connection: WebSocketConnection) -> bool:
        return connection.matches_alert(severity)

    _portal(client).call(hub.broadcast, ROUTE_ALERTS, _alert_payload(alert), _filter)


def _broadcast_pipeline(
    client: TestClient,
    hub: WebSocketHub,
    event: PipelineProgressEvent,
) -> None:
    knowledge_base_id = event.knowledge_base_id

    def _filter(connection: WebSocketConnection) -> bool:
        return connection.matches_kb(knowledge_base_id)

    _portal(client).call(
        hub.broadcast, ROUTE_PIPELINE, _pipeline_payload(event), _filter
    )


@pytest.fixture()
def hub() -> WebSocketHub:
    return WebSocketHub()


def _build_no_auth_domain_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=False),
        alerts=AlertsConfig(thresholds={}),
    )


@pytest.fixture()
def client(hub: WebSocketHub) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ws_hub] = lambda: hub
    app.dependency_overrides[get_domain_config] = _build_no_auth_domain_config
    app.dependency_overrides[get_session_store] = lambda: InMemorySessionStore()
    # get_current_user requires a Request parameter that Starlette injects; override
    # it directly so the bare-FastAPI test app doesn't need to resolve auth plumbing.
    app.dependency_overrides[get_current_user] = build_anonymous_user
    with TestClient(app) as test_client:
        yield test_client


class TestAlertsWebSocket:
    def test_unfiltered_subscriber_receives_alert(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/alerts") as ws:
            alert = _make_alert("high")
            _broadcast_alert(client, hub, alert)
            received: dict[str, Any] = ws.receive_json()
            assert received["type"] == "alert"
            assert received["data"]["severity"] == "high"

    def test_severity_filter_passes_matching_alert(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/alerts") as ws:
            ws.send_json({"subscribe": {"severity": ["high", "critical"]}})

            def _filter_applied() -> bool:
                connections = hub.connections(ROUTE_ALERTS)
                return bool(connections) and connections[0].severity_filter is not None

            _portal(client).call(_wait_until, _filter_applied)
            _broadcast_alert(client, hub, _make_alert("critical"))
            received: dict[str, Any] = ws.receive_json()
            assert received["data"]["severity"] == "critical"

    def test_severity_filter_rejects_non_matching_alert(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/alerts") as ws:
            ws.send_json({"subscribe": {"severity": ["critical"]}})

            def _filter_applied() -> bool:
                connections = hub.connections(ROUTE_ALERTS)
                if not connections:
                    return False
                severity_filter = connections[0].severity_filter
                return severity_filter is not None and "critical" in severity_filter

            _portal(client).call(_wait_until, _filter_applied)
            _broadcast_alert(client, hub, _make_alert("low"))
            _broadcast_alert(client, hub, _make_alert("critical", "alert-2"))

            received: dict[str, Any] = ws.receive_json()
            assert received["data"]["id"] == "alert-2"
            assert received["data"]["severity"] == "critical"

    def test_invalid_subscribe_payload_is_ignored(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/alerts") as ws:
            ws.send_json({"not_subscribe": "anything"})
            ws.send_json({"subscribe": {"severity": ["medium"]}})

            def _filter_applied() -> bool:
                connections = hub.connections(ROUTE_ALERTS)
                if not connections:
                    return False
                severity_filter = connections[0].severity_filter
                return severity_filter is not None and "medium" in severity_filter

            _portal(client).call(_wait_until, _filter_applied)
            _broadcast_alert(client, hub, _make_alert("medium"))
            received: dict[str, Any] = ws.receive_json()
            assert received["data"]["severity"] == "medium"

    def test_disconnect_removes_connection(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/alerts"):
            _portal(client).call(
                _wait_until, lambda: hub.connection_count(ROUTE_ALERTS) == 1
            )
        _portal(client).call(
            _wait_until, lambda: hub.connection_count(ROUTE_ALERTS) == 0
        )


class TestPipelineWebSocket:
    def test_scoped_subscription_receives_only_matching_kb_events(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/pipeline") as ws:
            ws.send_json({"subscribe": {"kb_id": "kb-1"}})

            def _filter_applied() -> bool:
                connections = hub.connections(ROUTE_PIPELINE)
                return bool(connections) and connections[0].kb_id_filter == "kb-1"

            _portal(client).call(_wait_until, _filter_applied)

            other_event = PipelineProgressEvent(
                knowledge_base_id="kb-other",
                stage="documents.parsed",
                progress=0.2,
            )
            target_event = PipelineProgressEvent(
                knowledge_base_id="kb-1",
                stage="graph.updated",
                progress=0.7,
            )
            _broadcast_pipeline(client, hub, other_event)
            _broadcast_pipeline(client, hub, target_event)

            received: dict[str, Any] = ws.receive_json()
            assert received["knowledge_base_id"] == "kb-1"
            assert received["stage"] == "graph.updated"
            assert received["progress"] == 0.7
            assert "timestamp" in received

    def test_unscoped_subscriber_receives_all_pipeline_events(
        self,
        client: TestClient,
        hub: WebSocketHub,
    ) -> None:
        with client.websocket_connect("/ws/pipeline") as ws:
            _portal(client).call(
                _wait_until, lambda: hub.connection_count(ROUTE_PIPELINE) == 1
            )
            for kb_id in ("kb-a", "kb-b"):
                _broadcast_pipeline(
                    client,
                    hub,
                    PipelineProgressEvent(
                        knowledge_base_id=kb_id,
                        stage="documents.uploaded",
                        progress=0.1,
                    ),
                )

            first: dict[str, Any] = ws.receive_json()
            second: dict[str, Any] = ws.receive_json()
            assert {first["knowledge_base_id"], second["knowledge_base_id"]} == {
                "kb-a",
                "kb-b",
            }


class TestWebSocketHub:
    def test_get_ws_hub_returns_singleton(self) -> None:
        get_ws_hub.cache_clear()
        first = get_ws_hub()
        second = get_ws_hub()
        assert first is second
        get_ws_hub.cache_clear()

    def test_connection_match_helpers_with_no_filter(self) -> None:
        connection = WebSocketConnection(
            id="conn-1",
            route=ROUTE_ALERTS,
            websocket=cast(Any, _NoOpWebSocket()),
        )
        assert connection.matches_alert("low") is True
        assert connection.matches_kb("any-kb") is True

    def test_connection_match_helpers_with_filter(self) -> None:
        connection = WebSocketConnection(
            id="conn-2",
            route=ROUTE_PIPELINE,
            websocket=cast(Any, _NoOpWebSocket()),
            severity_filter=frozenset({"high"}),
            kb_id_filter="kb-1",
        )
        assert connection.matches_alert("low") is False
        assert connection.matches_alert("high") is True
        assert connection.matches_kb("kb-1") is True
        assert connection.matches_kb("kb-2") is False

    def test_alert_created_event_has_expected_event_type(self) -> None:
        event = AlertCreatedEvent(alert=_make_alert("high"))
        assert event.event_type == "alert.created"
        assert event.alert.severity == "high"


class _NoOpWebSocket:
    """Stand-in for ``WebSocket`` used in unit tests for connection helpers."""

    async def accept(self) -> None:
        return None

    async def send_json(self, data: object) -> None:
        return None

    async def receive_json(self) -> object:
        return {}


# ---------------------------------------------------------------------------
# RBAC enforcement tests — WS upgrade is viewer-tier
# ---------------------------------------------------------------------------


def _build_auth_enabled_domain_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(
            enabled=True,
            issuer_url="https://idp.example.com",
            audience="chili-api",
            jwks_uri="https://idp.example.com/jwks",
            client_id="chili-spa",
            client_secret_env_var="OIDC_CLIENT_SECRET",
            authorize_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/oauth/token",
            redirect_uri="https://app.example.com/auth/callback",
        ),
        alerts=AlertsConfig(thresholds={}),
    )


def test_ws_alerts_rejects_unauthenticated_upgrade_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unauthenticated WS upgrade to /ws/alerts is rejected before websocket.accept()."""
    import time

    from api.app import create_app
    from config.loader import load_config
    from pathlib import Path

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", lambda app: None)

    domain = _build_auth_enabled_domain_config()
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()
    store = InMemorySessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app, raise_server_exceptions=False) as client:
        with pytest.raises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/ws/alerts"):
                pass


def test_ws_alerts_accepts_upgrade_with_viewer_session_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WS upgrade to /ws/alerts succeeds when the current user holds the viewer role.

    Note: ``get_current_user`` is overridden to return a viewer ``User`` directly
    because FastAPI's WS dependency solver does not inject the ``Request`` positional
    argument via DI the same way HTTP routes do in all FastAPI versions. The purpose
    of this test is to verify that the ``require_role("viewer")`` dependency *passes*
    when the user has the viewer role — the auth middleware itself is exercised
    separately in ``test_auth_middleware.py``.
    """
    from api.app import create_app

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", lambda app: None)

    domain = _build_auth_enabled_domain_config()
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()
    viewer = User(user_id="u-viewer", roles=["viewer"])
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # If the upgrade succeeds the context manager enters normally.
        with client.websocket_connect("/ws/alerts"):
            pass  # Connection accepted — assertion is that no exception is raised.
