"""Integration tests for the FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_graph_service as get_application_graph_service,
    get_object_store,
)
from api.middleware.auth import build_anonymous_user, get_current_user
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
    app.dependency_overrides[get_object_store] = lambda: InMemoryObjectStore()

    graph_service: GraphServiceProtocol = cast(
        GraphServiceProtocol,
        create_graph_service(
            InMemoryGraphRepository(),
            object_store=InMemoryObjectStore(),
            event_bus=InMemoryEventBus(),
        ),
    )
    app.dependency_overrides[get_application_graph_service] = lambda: graph_service
    app.dependency_overrides[get_investigation_graph_service] = lambda: graph_service
    # WS routes now require viewer via require_role; override get_current_user so
    # the anonymous viewer is resolved without needing the Request injection path.
    app.dependency_overrides[get_current_user] = build_anonymous_user

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
            "/knowledgebases/{knowledge_base_id}/score-runs",
            "/knowledgebases/{knowledge_base_id}/score-runs/{run_id}",
            "/knowledgebases/{knowledge_base_id}/score-runs/{run_id}/cancel",
            "/knowledgebases/{knowledge_base_id}/score-runs/{run_id}/replay",
            "/knowledgebases/{knowledge_base_id}/playbooks",
            "/knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/versions/{version}",
            "/knowledgebases/{knowledge_base_id}/playbooks/{playbook_id}/publish",
            "/knowledgebases/{knowledge_base_id}/playbooks/import",
            "/knowledgebases/{knowledge_base_id}/playbooks/export",
            "/alerts",
            "/alerts/{alert_id}",
            "/alerts/{alert_id}/acknowledge",
            "/investigation/entities/{entity_id}",
            "/investigation/entities/{entity_id}/neighborhood",
            "/investigation/search",
            "/chat/conversations/{conversation_id}/messages",
            "/analytics/risk-scores",
            "/analytics/risk-projections",
            "/analytics/risk-projections/rebuild",
            "/analytics/timeseries",
            "/analytics/gnn/clusters",
            "/identity/canonical/{entity_id}",
            "/identity/resolve-candidates",
            "/identity/links/{link_id}/decision",
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
            "score-runs",
            "playbooks",
            "identity",
        }.issubset(tags)

    def test_frontend_json_routes_have_response_schemas(self, client: TestClient) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        paths = cast(dict[str, dict[str, dict[str, object]]], schema["paths"])

        required_operations: tuple[tuple[str, str], ...] = (
            ("/config/domain", "get"),
            ("/config/features", "get"),
            ("/chat/conversations/{conversation_id}/messages", "post"),
            ("/investigation/search", "get"),
            ("/investigation/entities/{entity_id}/neighborhood", "get"),
            ("/knowledgebases/{knowledge_base_id}/score-runs", "post"),
            ("/knowledgebases/{knowledge_base_id}/score-runs/{run_id}", "get"),
        )

        missing: list[str] = []
        for path, method in required_operations:
            operation = paths[path][method]
            responses = cast(dict[str, object], operation["responses"])
            success = cast(dict[str, object], responses["200"])
            content = cast(dict[str, object], success.get("content", {}))
            json_content = cast(dict[str, object], content.get("application/json", {}))
            if "schema" not in json_content:
                missing.append(f"{method.upper()} {path}")

        assert missing == []

        chat_operation = paths["/chat/conversations/{conversation_id}/messages"]["post"]
        chat_responses = cast(dict[str, object], chat_operation["responses"])
        chat_success = cast(dict[str, object], chat_responses["200"])
        chat_content = cast(dict[str, object], chat_success["content"])
        chat_json = cast(dict[str, object], chat_content["application/json"])
        assert chat_json["schema"] == {
            "$ref": "#/components/schemas/ChatConversationResponse"
        }

    def test_openapi_response_schemas_do_not_use_json_schema_defs(
        self, client: TestClient
    ) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        paths = cast(dict[str, dict[str, dict[str, object]]], schema["paths"])
        bad_refs: list[str] = []

        def collect_bad_refs(value: object, location: str) -> None:
            if isinstance(value, dict):
                node = cast(dict[str, object], value)
                ref = node.get("$ref")
                if isinstance(ref, str) and ref.startswith("#/$defs/"):
                    bad_refs.append(f"{location}: {ref}")
                for key, child in node.items():
                    collect_bad_refs(child, f"{location}.{key}")
            elif isinstance(value, list):
                items = cast(list[object], value)
                for index, child in enumerate(items):
                    collect_bad_refs(child, f"{location}[{index}]")

        for path, operations in paths.items():
            for method, operation in operations.items():
                responses = cast(dict[str, object], operation.get("responses", {}))
                collect_bad_refs(responses, f"{method.upper()} {path}")

        assert bad_refs == []

    def test_domain_config_schema_includes_runtime_sections(self, client: TestClient) -> None:
        schema = cast(dict[str, object], client.get("/openapi.json").json())
        components = cast(dict[str, dict[str, object]], schema["components"])
        schemas = cast(dict[str, dict[str, object]], components["schemas"])
        domain_config = schemas["DomainConfig"]
        properties = cast(dict[str, object], domain_config["properties"])

        assert {"capabilities", "validation", "records", "ui", "alerts"}.issubset(
            properties
        )


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
