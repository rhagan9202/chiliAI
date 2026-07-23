"""Tests for the /events SSE router — verifies require_role enforcement."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from agent.protocols import AgentServiceProtocol
from agent.service import create_agent_service
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from api.dependencies import (
    get_agent_service,
    get_alert_feed_store,
    get_knowledge_base_repository,
)
from api.middleware.auth import get_current_user
from events.adapters.in_memory import InMemoryEventBus
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.adapters.protocols import AlertFeedStoreProtocol
from monitoring.models import AlertHistoryRecord
from shared.types import KnowledgeBase
from shared.utils import utc_now

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


def _skip_policy_audit(app: FastAPI) -> None:
    del app


def _seed_alert_store() -> AlertFeedStoreProtocol:
    """Return active and inactive alert history rows for SSE tests."""
    store = InMemoryAlertHistoryWriter()
    now = utc_now()
    store.write_alerts(
        [
            AlertHistoryRecord(
                knowledge_base_id="kb-1",
                alert_id="alert-active",
                entity_id="provider-204",
                entity_type="provider",
                severity="high",
                status="open",
                title="Active alert",
                reasoning="This alert should count as active.",
                metric_name="claims_per_week",
                created_at=now,
                updated_at=now,
                confidence=0.82,
            ),
            AlertHistoryRecord(
                knowledge_base_id="kb-1",
                alert_id="alert-resolved",
                entity_id="provider-118",
                entity_type="provider",
                severity="medium",
                status="resolved",
                title="Resolved alert",
                reasoning="This alert should not count as active.",
                metric_name="claims_per_week",
                created_at=now,
                updated_at=now,
                confidence=0.62,
            ),
        ]
    )
    return store


def _seed_agent_service() -> AgentServiceProtocol:
    """Return an agent service with active and completed workflows."""
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-queued",
                knowledge_base_id="kb-live-sse",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.QUEUED,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 5, 8, 13, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="workflow-running",
                knowledge_base_id="kb-live-sse",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="workflow-completed",
                knowledge_base_id="kb-live-sse",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 5, 8, 11, tzinfo=timezone.utc),
            ),
        ]
    )
    return create_agent_service(run_store, event_bus=InMemoryEventBus())


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


def test_events_stream_returns_cached_knowledge_base_statuses_without_graph_reads() -> None:
    """SSE status heartbeats avoid live graph projection to prevent idle churn."""
    from api.app import create_app

    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id="kb-live-sse",
            name="Live SSE KB",
            description="",
            status="building",
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
    alert_store = _seed_alert_store()
    agent_service = _seed_agent_service()
    app.dependency_overrides[get_alert_feed_store] = lambda: alert_store
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository

    with TestClient(app) as client:
        response = client.get("/events/stream", params={"max_events": 1})

    body = response.content.decode()
    assert response.status_code == 200
    assert '"active_alerts":1' in body
    assert '"running_workflows":2' in body
    assert '"knowledge_base_statuses":{"kb-live-sse":"building"}' in body
    assert "kb-1" not in body


def test_events_stream_counts_all_accessible_active_workflows_beyond_first_page() -> None:
    """SSE running_workflows scans every workflow page before counting active runs."""
    from api.app import create_app

    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id="kb-live-sse",
            name="Live SSE KB",
            description="",
            status="ready",
            created_at=utc_now(),
        )
    )
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id=f"workflow-{index}",
                knowledge_base_id="kb-live-sse",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 5, 8, 12, index % 60, tzinfo=timezone.utc),
            )
            for index in range(501)
        ]
    )
    agent_service = create_agent_service(run_store, event_bus=InMemoryEventBus())
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository

    with TestClient(app) as client:
        response = client.get("/events/stream", params={"max_events": 1})

    assert response.status_code == 200
    body = response.content.decode()
    assert '"running_workflows":501' in body


def test_events_stream_filters_snapshot_to_scoped_user_access() -> None:
    """Scoped viewers only see allowed KB statuses and active workflow counts."""
    from api.app import create_app

    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    scoped_kbs: list[
        tuple[str, Literal["active", "building", "ready", "error", "archived"]]
    ] = [
        ("kb-allowed", "building"),
        ("kb-denied", "ready"),
    ]
    for kb_id, status in scoped_kbs:
        repository.create(
            KnowledgeBase(
                id=kb_id,
                name=kb_id,
                description="",
                status=status,
                created_at=utc_now(),
            )
        )
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="allowed-running",
                knowledge_base_id="kb-allowed",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            ),
            WorkflowRun(
                workflow_id="allowed-queued",
                knowledge_base_id="kb-allowed",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.QUEUED,
                steps=[WorkflowStepState(step_name="parse")],
            ),
            WorkflowRun(
                workflow_id="denied-running",
                knowledge_base_id="kb-denied",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            ),
        ]
    )
    agent_service = create_agent_service(run_store, event_bus=InMemoryEventBus())
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="scoped-viewer",
        roles=["viewer"],
        email="scoped-viewer@example.com",
        knowledge_base_ids=["kb-allowed"],
    )

    with TestClient(app) as client:
        response = client.get("/events/stream", params={"max_events": 1})

    assert response.status_code == 200
    body = response.content.decode()
    assert '"running_workflows":2' in body
    assert '"knowledge_base_statuses":{"kb-allowed":"building"}' in body
    assert "kb-denied" not in body


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
