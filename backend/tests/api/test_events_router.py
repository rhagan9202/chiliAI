"""Tests for the /events SSE router — verifies require_role enforcement."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api._alert_store import AlertProjectionRecord, InMemoryAlertProjectionRepository
from api._kb_store import DocumentRecord, InMemoryKnowledgeBaseRepository
from api.dependencies import (
    get_alert_repository,
    get_graph_service,
    get_knowledge_base_repository,
    get_object_store,
)
from graph.models import GraphMetrics
from shared.types import Alert, KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


class _MetricsOnlyGraphService:
    def __init__(self, metrics: GraphMetrics) -> None:
        self._metrics = metrics

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics:
        del knowledge_base_id
        return self._metrics


def _skip_policy_audit(app: FastAPI) -> None:
    del app


def _seed_alert_repository() -> InMemoryAlertProjectionRepository:
    """Return active and inactive alert projections for SSE tests."""
    repository = InMemoryAlertProjectionRepository()
    repository.upsert(
        AlertProjectionRecord(
            alert=Alert(
                id="alert-active",
                entity_type="provider",
                entity_id="provider-204",
                severity="high",
                title="Active alert",
                reasoning="This alert should count as active.",
                created_at=utc_now(),
            ),
            confidence=0.82,
        )
    )
    repository.upsert(
        AlertProjectionRecord(
            alert=Alert(
                id="alert-resolved",
                entity_type="provider",
                entity_id="provider-118",
                severity="medium",
                title="Resolved alert",
                reasoning="This alert should not count as active.",
                created_at=utc_now(),
                status="resolved",
            ),
            confidence=0.62,
        )
    )
    return repository


def test_events_stream_returns_snapshot_when_auth_disabled() -> None:
    """In dev (auth disabled), an unauthenticated GET to /events/stream succeeds."""
    from api.app import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/events/stream", params={"max_events": 1})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.content.decode()
        assert "workspace-update" in body


def test_events_stream_returns_live_knowledge_base_statuses() -> None:
    """SSE KB statuses come from the live repository projection, not ApiState seeds."""
    from api.app import create_app

    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    object_store = InMemoryObjectStore()
    repository.create(
        KnowledgeBase(
            id="kb-live-sse",
            name="Live SSE KB",
            description="",
            status="active",
            created_at=utc_now(),
        )
    )
    repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-live-sse",
            filename="claims.json",
            status="registered",
        )
    )
    graph_service = _MetricsOnlyGraphService(
        GraphMetrics(entity_count=2, relationship_count=1, avg_degree=1.0)
    )
    alert_repository = _seed_alert_repository()
    app.dependency_overrides[get_alert_repository] = lambda: alert_repository
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_object_store] = lambda: object_store

    with TestClient(app) as client:
        response = client.get("/events/stream", params={"max_events": 1})

    body = response.content.decode()
    assert response.status_code == 200
    assert '"active_alerts":1' in body
    assert '"knowledge_base_statuses":{"kb-live-sse":"ready"}' in body
    assert "kb-1" not in body


def test_events_stream_rejects_anonymous_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With auth enabled, /events/stream 401s without a session cookie."""
    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore
    from config.loader import load_config
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", _skip_policy_audit)

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
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # No cookie -> 401 BEFORE the SSE generator runs.
        response = client.get("/events/stream", params={"max_events": 1})
        assert response.status_code == 401


def test_events_stream_accepts_viewer_session_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With auth enabled, a viewer session cookie passes the role guard."""
    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", _skip_policy_audit)

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
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get("/events/stream", params={"max_events": 1})
        assert response.status_code == 200
