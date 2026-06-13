"""Role-enforcement tests for the workflow status router."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from agent.service import create_agent_service
from api.app import create_app
from api.dependencies import get_agent_service, get_domain_config, get_session_store
from api.middleware.auth import get_current_user
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


def _app_with_workflows_and_auth(
    runs: list[WorkflowRun] | None = None,
) -> FastAPI:
    app = create_app()
    store = InMemorySessionStore()
    _save_session(store, session_id="sid-viewer", roles=["viewer"])
    _save_session(store, session_id="sid-analyst", roles=["analyst"])
    _save_session(store, session_id="sid-no-role", roles=[])
    run_store = InMemoryWorkflowRunStore(
        runs=runs
        or [
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


def _app_with_workflows_and_scoped_user(
    *,
    runs: list[WorkflowRun],
    roles: list[str],
) -> FastAPI:
    app = create_app()
    run_store = InMemoryWorkflowRunStore(runs=runs)
    agent_service = create_agent_service(run_store, event_bus=InMemoryEventBus())
    app.dependency_overrides[get_domain_config] = _domain_with_auth
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="scoped-user",
        roles=roles,
        email="scoped-user@example.com",
        knowledge_base_ids=["kb-1"],
    )
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
    assert response.json()["has_more"] is False
    assert response.json()["next_offset"] is None


def test_list_workflows_returns_pagination_metadata_when_auth_enabled() -> None:
    app = _app_with_workflows_and_auth(
        runs=[
            WorkflowRun(
                workflow_id=f"workflow-{index}",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            )
            for index in range(3)
        ]
    )

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get("/workflows", params={"limit": 2, "offset": 0})

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["has_more"] is True
    assert response.json()["next_offset"] == 2


def test_user_without_roles_cannot_list_workflows_when_auth_enabled() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-no-role")
        response = client.get("/workflows")

    assert response.status_code == 403


def test_list_workflows_applies_query_filters_when_auth_enabled() -> None:
    app = _app_with_workflows_and_auth(
        runs=[
            WorkflowRun(
                workflow_id="target",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="ready")],
            ),
            WorkflowRun(
                workflow_id="other-kb",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="ready")],
            ),
            WorkflowRun(
                workflow_id="other-status",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            ),
        ]
    )

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get(
            "/workflows",
            params={
                "knowledge_base_id": "kb-1",
                "status": "completed",
                "limit": 10,
                "offset": 0,
            },
        )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["target"]


def test_list_workflows_filters_runs_outside_user_knowledge_base_scope() -> None:
    app = _app_with_workflows_and_scoped_user(
        roles=["viewer"],
        runs=[
            WorkflowRun(
                workflow_id="allowed",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            ),
            WorkflowRun(
                workflow_id="denied",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            ),
        ],
    )

    response = TestClient(app).get("/workflows")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["allowed"]


def test_list_workflows_fills_scoped_page_after_denied_newer_run() -> None:
    app = _app_with_workflows_and_scoped_user(
        roles=["viewer"],
        runs=[
            WorkflowRun(
                workflow_id="allowed",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="denied-newer",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ],
    )

    response = TestClient(app).get("/workflows", params={"limit": 1, "offset": 0})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["allowed"]
    assert response.json()["has_more"] is False
    assert response.json()["next_offset"] is None


def test_list_workflows_uses_store_cursor_for_scoped_second_page() -> None:
    app = _app_with_workflows_and_scoped_user(
        roles=["viewer"],
        runs=[
            WorkflowRun(
                workflow_id="allowed-old",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="allowed-mid",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="denied-newer",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
        ],
    )

    first_response = TestClient(app).get(
        "/workflows", params={"limit": 1, "offset": 0}
    )

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert [item["id"] for item in first_body["items"]] == ["allowed-mid"]
    assert first_body["has_more"] is True
    assert first_body["next_offset"] == 2

    second_response = TestClient(app).get(
        "/workflows", params={"limit": 1, "offset": first_body["next_offset"]}
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert [item["id"] for item in second_body["items"]] == ["allowed-old"]
    assert second_body["has_more"] is False
    assert second_body["next_offset"] is None


def test_get_workflow_returns_run_for_viewer() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get("/workflows/workflow-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "workflow-1"
    assert body["status"] == "running"


def test_get_workflow_returns_404_for_unknown_id() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.get("/workflows/missing")

    assert response.status_code == 404


def test_get_workflow_returns_404_for_run_outside_user_knowledge_base_scope() -> None:
    app = _app_with_workflows_and_scoped_user(
        roles=["viewer"],
        runs=[
            WorkflowRun(
                workflow_id="denied",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            )
        ],
    )

    response = TestClient(app).get("/workflows/denied")

    assert response.status_code == 404


def test_cancel_workflow_transitions_running_to_cancelled() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-analyst")
        response = client.post("/workflows/workflow-1/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_workflow_requires_analyst_role() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        response = client.post("/workflows/workflow-1/cancel")

    assert response.status_code == 403


def test_cancel_workflow_returns_404_for_unknown_id() -> None:
    app = _app_with_workflows_and_auth()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-analyst")
        response = client.post("/workflows/missing/cancel")

    assert response.status_code == 404


def test_cancel_workflow_returns_404_for_run_outside_user_knowledge_base_scope() -> None:
    app = _app_with_workflows_and_scoped_user(
        roles=["analyst"],
        runs=[
            WorkflowRun(
                workflow_id="denied",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            )
        ],
    )

    response = TestClient(app).post("/workflows/denied/cancel")

    assert response.status_code == 404


def test_cancel_workflow_returns_409_when_already_terminal() -> None:
    app = _app_with_workflows_and_auth(
        runs=[
            WorkflowRun(
                workflow_id="done-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="ready")],
            )
        ]
    )

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-analyst")
        response = client.post("/workflows/done-1/cancel")

    assert response.status_code == 409
