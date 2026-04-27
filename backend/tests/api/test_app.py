"""Integration tests for the FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config
from api.routers.investigation import get_graph_service as get_investigation_graph_service
from config.loader import load_config
from config.schema import DomainConfig
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.protocols import GraphServiceProtocol
from graph.service import create_graph_service
from storage.adapters.in_memory import InMemoryObjectStore

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


@pytest.fixture()
def domain_config() -> DomainConfig:
    return load_config(MEDICARE_YAML)


@pytest.fixture()
def client(domain_config: DomainConfig) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: domain_config

    graph_service: GraphServiceProtocol = cast(
        GraphServiceProtocol,
        create_graph_service(
            InMemoryGraphRepository(),
            object_store=InMemoryObjectStore(),
            event_bus=InMemoryEventBus(),
        ),
    )
    app.dependency_overrides[get_investigation_graph_service] = lambda: graph_service

    return TestClient(app)


class TestHealthRoute:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestRouterRegistration:
    """Verify every router required by E5-S14 is registered in the app factory."""

    def test_config_router_is_registered(self, client: TestClient) -> None:
        response = client.get("/config/domain")
        assert response.status_code == 200

    def test_knowledgebases_router_is_registered(self, client: TestClient) -> None:
        response = client.get("/knowledgebases")
        assert response.status_code == 200

    def test_alerts_router_is_registered(self, client: TestClient) -> None:
        response = client.get("/alerts")
        assert response.status_code == 200

    def test_investigation_router_is_registered(self, client: TestClient) -> None:
        # Missing required ``kb_id`` query parameter -> 422 (validation), not 404.
        response = client.get("/investigation/search")
        assert response.status_code == 422

    def test_chat_router_is_registered(self, client: TestClient) -> None:
        # POST endpoint exists; missing body yields 422 (validation), not 404.
        response = client.post("/chat/conversations/abc/messages")
        assert response.status_code == 422

    def test_analytics_router_is_registered(self, client: TestClient) -> None:
        # ``/analytics/risk-scores`` requires ``kb_id`` -> 422 when omitted.
        response = client.get("/analytics/risk-scores")
        assert response.status_code == 422


class TestOpenApiSchema:
    """Smoke test the generated OpenAPI document.

    The schema must enumerate every prefix wired in :func:`create_app`. We
    assert membership of expected paths rather than exact equality so future
    additions to the gateway do not break this test.
    """

    def test_openapi_returns_200(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_openapi_lists_all_required_paths(self, client: TestClient) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        paths = cast(dict[str, object], schema["paths"])

        expected: set[str] = {
            "/health",
            "/config/domain",
            "/knowledgebases",
            "/knowledgebases/{knowledge_base_id}",
            "/knowledgebases/{knowledge_base_id}/documents",
            "/knowledgebases/{knowledge_base_id}/documents/{document_id}",
            "/alerts",
            "/alerts/{alert_id}/acknowledge",
            "/alerts/{alert_id}/resolve",
            "/investigation/entities/{entity_id}",
            "/investigation/entities/{entity_id}/neighborhood",
            "/investigation/search",
            "/chat/conversations/{conversation_id}/messages",
            "/analytics/risk-scores",
            "/analytics/timeseries",
            "/analytics/gnn/clusters",
        }

        missing = expected - set(paths)
        assert missing == set(), f"OpenAPI is missing paths: {sorted(missing)}"

    def test_openapi_tags_cover_all_routers(self, client: TestClient) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        paths = cast(dict[str, dict[str, object]], schema["paths"])

        tags: set[str] = set()
        for operations in paths.values():
            for operation in operations.values():
                op = cast(dict[str, object], operation)
                operation_tags = op.get("tags")
                if isinstance(operation_tags, list):
                    raw_tags = cast(list[object], operation_tags)
                    for tag in raw_tags:
                        if isinstance(tag, str):
                            tags.add(tag)

        assert {
            "configuration",
            "knowledge-bases",
            "alerts",
            "investigation",
            "chat",
            "analytics",
        }.issubset(tags)


class TestWebSocketRouter:
    """The WebSocket router is registered too, but cannot be hit via HTTP GET.

    We exercise the WS path using ``TestClient.websocket_connect`` which only
    succeeds when the router is wired into the app factory.
    """

    def test_alerts_websocket_accepts_connections(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/alerts") as websocket:
            # The router accepts the connection and waits for subscribe messages.
            # We close immediately; a successful handshake is enough to prove
            # registration.
            websocket.close()

    def test_pipeline_websocket_accepts_connections(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/pipeline") as websocket:
            websocket.close()
