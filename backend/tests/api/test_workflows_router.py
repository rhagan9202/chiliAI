"""Role-enforcement tests for the workflow status router."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from agent.service import create_agent_service
from api.app import create_app
from api.dependencies import get_agent_service, get_domain_config, get_session_store
from api.middleware.session_store import InMemorySessionStore, SessionRecord
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from events.adapters.in_memory import InMemoryEventBus


def _domain_with_auth() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _save_session(
    store: InMemorySessionStore,
    *,
    session_id: str,
    roles: list[str],
) -> None:
    now = time.time()
    store.save(
        SessionRecord(
            session_id=session_id,
            user_id=session_id,
            roles=roles,
            email=f"{session_id}@example.com",
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_at=now + 3600,
            id_token="id-token",
            created_at=now,
            ttl_seconds=3600,
        )
    )


def _app_with_workflows_and_auth() -> FastAPI:
    app = create_app()
    store = InMemorySessionStore()
    _save_session(store, session_id="sid-viewer", roles=["viewer"])
    _save_session(store, session_id="sid-no-role", roles=[])
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            )
        ]
    )
    agent_service = create_agent_service(run_store, event_bus=InMemoryEventBus())
    app.dependency_overrides[get_domain_config] = _domain_with_auth
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    return app


def test_list_workflows_requires_authentication_when_auth_enabled() -> None:
    app = _app_with_workflows_and_auth()

    response = TestClient(app).get("/workflows")

    assert response.status_code == 401


def test_viewer_can_list_workflows_when_auth_enabled() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get("/workflows")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "workflow-1"


def test_user_without_roles_cannot_list_workflows_when_auth_enabled() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-no-role")
        response = client.get("/workflows")

    assert response.status_code == 403
