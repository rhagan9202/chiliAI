"""Tests for KB-scoped workflow definition API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_workflow_definition_service,
)
from api.middleware.auth import User, get_current_user
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEventQuery
from auditlog.service import AuditLogService
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.service import WorkflowDefinitionService


BASE_TIME = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
KB_ID = "kb-workflows"
BASE_URL = f"/knowledgebases/{KB_ID}/workflow-definitions"


def _domain_config() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _knowledge_base_repository() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id=KB_ID,
            name="Workflow KB",
            description="Workflow definition API test KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    return repository


def _create_payload(
    *,
    definition_id: str = "provider-review",
    capability_ref: str = "rag.query",
) -> dict[str, Any]:
    return {
        "definition_id": definition_id,
        "name": "Provider review",
        "version": "v1",
        "description": "Review suspicious provider behavior.",
        "allowed_capability_refs": [capability_ref],
        "steps": [
            {
                "step_id": "ask-rag",
                "label": "Ask RAG",
                "capability_ref": capability_ref,
                "input_refs": ["alert.summary"],
                "output_refs": ["draft.findings"],
                "on_failure": "fail_workflow",
            }
        ],
    }


def _run_payload(*, idempotency_key: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target_type": "alert",
        "target_id": "alert-123",
        "inputs": {"priority": "high", "score": 0.91, "expedite": True},
    }
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return payload


def _user(
    role: str,
    *,
    knowledge_base_ids: list[str] | None = None,
) -> User:
    return User(
        user_id=f"{role}-1",
        roles=[role],
        email=f"{role}-1@example.test",
        knowledge_base_ids=knowledge_base_ids if knowledge_base_ids is not None else [KB_ID],
    )


def _set_user(app: FastAPI, user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _app_harness() -> tuple[
    FastAPI,
    InMemoryWorkflowDefinitionRepository,
    InMemoryWorkflowRunStore,
    AuditLogService,
]:
    app = create_app()
    definition_repository = InMemoryWorkflowDefinitionRepository()
    run_store = InMemoryWorkflowRunStore()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    service = WorkflowDefinitionService(
        definition_repository,
        run_store,
        audit_service,
    )
    app.dependency_overrides[get_domain_config] = _domain_config
    app.dependency_overrides[get_knowledge_base_repository] = _knowledge_base_repository
    app.dependency_overrides[get_workflow_definition_service] = lambda: service
    return app, definition_repository, run_store, audit_service


def _audit_correlation_id(
    audit_service: AuditLogService,
    *,
    action: str,
) -> str:
    events = audit_service.list_events(
        AuditEventQuery(action_prefix=action)
    ).items
    assert len(events) == 1
    return events[0].correlation_id


def _create_and_approve_definition(
    client: TestClient,
    app: FastAPI,
    *,
    definition_id: str = "provider-review",
) -> None:
    _set_user(app, _user("analyst"))
    created = client.post(BASE_URL, json=_create_payload(definition_id=definition_id))
    assert created.status_code == 200
    _set_user(app, _user("admin"))
    approved = client.post(
        f"{BASE_URL}/{definition_id}/versions/v1/approve",
        headers={"x-request-id": "approve-request"},
    )
    assert approved.status_code == 200


def test_analyst_can_create_draft_and_list_detail_it() -> None:
    app, _, _, _ = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        created = client.post(BASE_URL, json=_create_payload())
        listed = client.get(BASE_URL)
        detail = client.get(f"{BASE_URL}/provider-review/versions/v1")

    assert created.status_code == 200
    assert created.json()["definition_id"] == "provider-review"
    assert created.json()["status"] == "draft"
    assert created.json()["knowledge_base_id"] == KB_ID
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["definition_id"] == "provider-review"
    assert detail.status_code == 200
    assert detail.json()["steps"][0]["step_id"] == "ask-rag"


def test_viewer_cannot_create_definition_when_auth_enabled() -> None:
    app, _, _, _ = _app_harness()
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.post(BASE_URL, json=_create_payload())

    assert response.status_code == 403


def test_admin_can_approve_then_analyst_can_run_approved_definition() -> None:
    app, _, _, audit_service = _app_harness()

    with TestClient(app) as client:
        _create_and_approve_definition(client, app)
        _set_user(app, _user("analyst"))
        response = client.post(
            f"{BASE_URL}/provider-review/versions/v1/run",
            json=_run_payload(idempotency_key="run-123"),
            headers={"x-correlation-id": "run-request"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["knowledge_base_id"] == KB_ID
    assert body["current_step"] == "ask-rag"
    assert (
        _audit_correlation_id(
            audit_service,
            action="workflow_definition.run_requested",
        )
        == "run-request"
    )


def test_analyst_cannot_approve_definition() -> None:
    app, _, _, _ = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        created = client.post(BASE_URL, json=_create_payload())
        response = client.post(f"{BASE_URL}/provider-review/versions/v1/approve")

    assert created.status_code == 200
    assert response.status_code == 403


def test_run_draft_returns_409() -> None:
    app, _, _, _ = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        created = client.post(BASE_URL, json=_create_payload())
        response = client.post(
            f"{BASE_URL}/provider-review/versions/v1/run",
            json=_run_payload(),
        )

    assert created.status_code == 200
    assert response.status_code == 409


def test_out_of_scope_knowledge_base_returns_404() -> None:
    app, _, _, _ = _app_harness()
    _set_user(app, _user("analyst", knowledge_base_ids=["kb-other"]))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 404


def test_invalid_capability_returns_422_and_does_not_persist() -> None:
    app, repository, _, _ = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        response = client.post(
            BASE_URL,
            json=_create_payload(capability_ref="unknown.capability"),
        )

    assert response.status_code == 422
    assert repository.list_definitions(knowledge_base_id=KB_ID).items == []


def test_create_accepts_registered_connector_status_capability() -> None:
    app, _, _, _ = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        response = client.post(
            BASE_URL,
            json=_create_payload(capability_ref="connector.sync.status"),
        )

    assert response.status_code == 200
    assert response.json()["steps"][0]["capability_ref"] == "connector.sync.status"


def test_admin_can_retire_approved_definition_and_analyst_run_retired_returns_409() -> None:
    app, _, _, _ = _app_harness()

    with TestClient(app) as client:
        _create_and_approve_definition(client, app)
        _set_user(app, _user("admin"))
        retired = client.post(f"{BASE_URL}/provider-review/versions/v1/retire")
        _set_user(app, _user("analyst"))
        run = client.post(
            f"{BASE_URL}/provider-review/versions/v1/run",
            json=_run_payload(),
        )

    assert retired.status_code == 200
    assert retired.json()["status"] == "retired"
    assert run.status_code == 409


def test_run_idempotency_replay_with_same_key_returns_same_workflow_id() -> None:
    app, _, run_store, _ = _app_harness()

    with TestClient(app) as client:
        _create_and_approve_definition(client, app)
        _set_user(app, _user("analyst"))
        first = client.post(
            f"{BASE_URL}/provider-review/versions/v1/run",
            json=_run_payload(idempotency_key="idem-123"),
        )
        second = client.post(
            f"{BASE_URL}/provider-review/versions/v1/run",
            json=_run_payload(idempotency_key="idem-123"),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert len(run_store.list_runs(knowledge_base_id=KB_ID).items) == 1


def test_create_without_correlation_header_uses_workflow_definition_fallback() -> None:
    app, _, _, audit_service = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        response = client.post(BASE_URL, json=_create_payload())

    assert response.status_code == 200
    assert (
        _audit_correlation_id(
            audit_service,
            action="workflow_definition.created",
        )
        == "workflow-definition-request"
    )
