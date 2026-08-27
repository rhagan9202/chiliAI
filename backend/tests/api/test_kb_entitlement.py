"""The KB entitlement gate on workflow and event routes.

``_can_access_workflow`` / ``_can_access_knowledge_base`` read
``knowledge_base_ids`` off the authenticated principal, but ``User`` never
carried that field and Pydantic ignores unknown claims — so the lookup was
always ``None``, the guard always returned True, and the 404 branches were
unreachable. It read as enforced tenancy while enforcing nothing.
"""

from __future__ import annotations

import pathlib
import time
from datetime import datetime, timezone

from fastapi import FastAPI
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
from api.dependencies import get_agent_service, get_domain_config, get_session_store
from api.middleware.auth import SESSION_COOKIE_NAME, User, get_current_user
from api.middleware.session_store import InMemorySessionStore, SessionRecord
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from events.adapters.in_memory import InMemoryEventBus

_MEDICARE_YAML = (
    pathlib.Path(__file__).resolve().parents[2] / "config" / "defaults" / "medicare_fraud.yaml"
)


def _workflow_app() -> FastAPI:
    """App serving one workflow run that lives in ``kb-1``."""

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
    return app


def _client_with_workflow(user: User) -> TestClient:
    app = _workflow_app()
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _auth_enabled_domain_config() -> DomainConfig:
    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    return load_config(_MEDICARE_YAML).model_copy(update={"auth": auth_cfg})


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


class TestEntitlementSurvivesTheCookieSessionPath:
    """The gate above is exercised with a hand-built ``User``.

    Every browser request arrives on the cookie/session path instead, which
    rebuilds the principal from a ``SessionRecord``. These tests drive that
    real path — no ``get_current_user`` override — so a claim dropped between
    the IdP and the rebuilt ``User`` cannot pass unnoticed.
    """

    def _client(self, knowledge_base_ids: list[str] | None) -> TestClient:
        domain = _auth_enabled_domain_config()
        store = InMemorySessionStore()
        store.save(
            SessionRecord(
                session_id="sid-1",
                user_id="analyst-1",
                roles=["analyst"],
                email="analyst@example.com",
                knowledge_base_ids=knowledge_base_ids,
                access_token="acc",
                refresh_token="ref",
                access_token_expires_at=time.time() + 3600,
                id_token="id",
                created_at=time.time(),
                ttl_seconds=3600,
            )
        )
        app = _workflow_app()
        app.dependency_overrides[get_domain_config] = lambda: domain
        app.dependency_overrides[get_session_store] = lambda: store
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE_NAME, "sid-1")
        return client

    def test_a_session_entitlement_denies_a_knowledge_base_outside_the_claim(self) -> None:
        response = self._client(["kb-other"]).get("/workflows/workflow-kb-1")

        assert response.status_code == 404

    def test_a_session_entitlement_allows_a_knowledge_base_named_in_the_claim(self) -> None:
        response = self._client(["kb-1"]).get("/workflows/workflow-kb-1")

        assert response.status_code == 200

    def test_a_session_without_the_claim_stays_unrestricted(self) -> None:
        response = self._client(None).get("/workflows/workflow-kb-1")

        assert response.status_code == 200
