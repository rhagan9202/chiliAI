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


def test_pagination_does_not_drop_accessible_runs_inside_a_page() -> None:
    """The inner scan loop breaks as soon as the limit is filled, which can
    happen partway through an underlying store page. next_offset must resume
    at the first unconsumed item in that page, not at the page's end -- else
    every accessible run between the two is silently skipped.

    Two denied runs occupy all of the first store page (limit=3), so the scan
    has to fetch a second page to fill the limit. That second page holds
    three items but only the first two are needed to reach the limit --
    "wf-D" is the unconsumed third item that the bug drops.
    """
    app = _app_with_workflows_and_scoped_user(
        roles=["viewer"],
        runs=[
            WorkflowRun(
                workflow_id="denied-0",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="denied-1",
                knowledge_base_id="kb-2",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 9, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="wf-a",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 8, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="wf-b",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 7, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="wf-c",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 6, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="wf-d",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="wf-e",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            ),
        ],
    )

    first_response = TestClient(app).get(
        "/workflows", params={"limit": 3, "offset": 0}
    )

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert [item["id"] for item in first_body["items"]] == ["wf-a", "wf-b", "wf-c"]
    assert first_body["has_more"] is True

    second_response = TestClient(app).get(
        "/workflows", params={"limit": 3, "offset": first_body["next_offset"]}
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    # "wf-d" is the run the buggy cursor skips -- it must be the first item
    # on the next page, not "wf-e".
    assert [item["id"] for item in second_body["items"]] == ["wf-d", "wf-e"]


def test_list_workflows_with_limit_zero_returns_no_items() -> None:
    """limit=0 is allowed by the route (`ge=0`) and takes a dedicated branch
    that never calls the entitlement-scan loop -- confirm it still behaves
    sanely for an entitled user rather than erroring or scanning forever.
    """
    app = _app_with_workflows_and_scoped_user(
        roles=["viewer"],
        runs=[
            WorkflowRun(
                workflow_id="wf-a",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            )
        ],
    )

    response = TestClient(app).get("/workflows", params={"limit": 0, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []


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


# ---------------------------------------------------------------------------
# Human approval decisions
#
# Asserted through the HTTP response, not the run store: `AWAITING_APPROVAL`
# was correct in the store and wrong in the API for the whole life of the
# feature because every test asserted the record behind the projection.
# ---------------------------------------------------------------------------


def _parked_run(workflow_id: str = "workflow-parked") -> WorkflowRun:
    return WorkflowRun(
        workflow_id=workflow_id,
        knowledge_base_id="kb-1",
        trigger_event_type="workflow_definition.requested",
        status=WorkflowRunStatus.AWAITING_APPROVAL,
        steps=[WorkflowStepState(step_name="gate"), WorkflowStepState(step_name="after")],
        metadata={"definition_id": "triage", "definition_version": "v1"},
        actor_user_id="analyst-1",
        actor_roles=["analyst"],
    )


def _app_with_approver(runs: list[WorkflowRun]) -> FastAPI:
    """`admin` is the platform role that approves; "supervisor" is a pack role."""
    app = _app_with_workflows_and_auth(runs=runs)
    store = app.dependency_overrides[get_session_store]()
    _save_session(store, session_id="sid-admin", roles=["admin"])
    return app


def test_approving_a_parked_step_returns_the_released_run() -> None:
    app = _app_with_approver([_parked_run()])

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-admin")
        response = client.post(
            "/workflows/workflow-parked/steps/gate/approve",
            json={},
        )

    assert response.status_code == 200, response.text
    # The projection, not the store: an approved run must not read as failed.
    assert response.json()["status"] == "queued"


def test_rejecting_a_parked_step_returns_a_failed_run() -> None:
    app = _app_with_approver([_parked_run()])

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-admin")
        response = client.post(
            "/workflows/workflow-parked/steps/gate/reject",
            json={"reason": "insufficient evidence"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["last_error"] == "insufficient evidence"


def test_rejecting_without_a_reason_is_a_validation_error() -> None:
    """"Rejected" with no reason is an audit record that explains nothing."""
    app = _app_with_approver([_parked_run()])

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-admin")
        response = client.post(
            "/workflows/workflow-parked/steps/gate/reject",
            json={},
        )

    assert response.status_code == 422


def test_approving_a_run_that_is_not_parked_is_a_conflict_not_a_404() -> None:
    """Wrong state and missing run are different things to an operator."""
    app = _app_with_approver(
        [
            WorkflowRun(
                workflow_id="workflow-running",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
            )
        ]
    )

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-admin")
        response = client.post(
            "/workflows/workflow-running/steps/parse/approve",
            json={},
        )

    assert response.status_code == 409, response.text


def test_approving_an_unknown_run_is_a_404() -> None:
    app = _app_with_approver([_parked_run()])

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-admin")
        response = client.post(
            "/workflows/no-such-run/steps/gate/approve",
            json={},
        )

    assert response.status_code == 404


def test_an_analyst_may_not_approve() -> None:
    """The gate requires a role the requester typically does not hold."""
    app = _app_with_approver([_parked_run()])

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-analyst")
        response = client.post(
            "/workflows/workflow-parked/steps/gate/approve",
            json={},
        )

    assert response.status_code == 403
