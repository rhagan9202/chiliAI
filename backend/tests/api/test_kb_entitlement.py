"""The KB entitlement gate on workflow and event routes.

``_can_access_workflow`` / ``_can_access_knowledge_base`` read
``knowledge_base_ids`` off the authenticated principal, but ``User`` never
carried that field and Pydantic ignores unknown claims — so the lookup was
always ``None``, the guard always returned True, and the 404 branches were
unreachable. It read as enforced tenancy while enforcing nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepState,
    WorkflowStepStatus,
)
from agent.service import create_agent_service
from api.app import create_app
from api.dependencies import get_agent_service
from api.middleware.auth import User, get_current_user
from events.adapters.in_memory import InMemoryEventBus


def _client_with_workflow(user: User) -> TestClient:
    app = create_app()
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-kb-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[
                    WorkflowStepState(
                        step_name="parse",
                        status=WorkflowStepStatus.COMPLETED,
                    )
                ],
                created_at=datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
            )
        ]
    )
    agent_service = create_agent_service(run_store, event_bus=InMemoryEventBus())
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_entitlement_denies_a_knowledge_base_outside_the_claim() -> None:
    client = _client_with_workflow(
        User(user_id="analyst-1", roles=["analyst"], knowledge_base_ids=["kb-other"])
    )

    response = client.get("/workflows/workflow-kb-1")

    assert response.status_code == 404


def test_entitlement_allows_a_knowledge_base_named_in_the_claim() -> None:
    client = _client_with_workflow(
        User(user_id="analyst-1", roles=["analyst"], knowledge_base_ids=["kb-1"])
    )

    response = client.get("/workflows/workflow-kb-1")

    assert response.status_code == 200


def test_absent_entitlement_claim_stays_unrestricted() -> None:
    """No claim means the IdP issues none; the gate must not lock everyone out."""
    client = _client_with_workflow(User(user_id="analyst-1", roles=["analyst"]))

    response = client.get("/workflows/workflow-kb-1")

    assert response.status_code == 200


def test_admin_bypasses_the_entitlement_claim() -> None:
    client = _client_with_workflow(
        User(user_id="root", roles=["admin"], knowledge_base_ids=["kb-other"])
    )

    response = client.get("/workflows/workflow-kb-1")

    assert response.status_code == 200
