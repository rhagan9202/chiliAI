"""Tests for SAFE-CMS-017 KB-scoped connector API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import (
    get_connector_service,
    get_domain_config,
    get_knowledge_base_repository,
)
from api.middleware.auth import User, get_current_user
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
)
from connectors.service import ConnectorService
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import KnowledgeBase

BASE_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
KB_ID = "kb-connectors"
BASE_URL = f"/knowledgebases/{KB_ID}/connectors"


def _domain_config() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _knowledge_base_repository() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id=KB_ID,
            name="Connector KB",
            description="Connector API test KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    return repository


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


def _app_harness() -> tuple[FastAPI, ConnectorService]:
    app = create_app()
    service = ConnectorService(InMemoryConnectorRepository())
    app.dependency_overrides[get_domain_config] = _domain_config
    app.dependency_overrides[get_knowledge_base_repository] = _knowledge_base_repository
    app.dependency_overrides[get_connector_service] = lambda: service
    return app, service


def _connector_payload() -> dict[str, object]:
    return {
        "connector_id": "cms-claims-drop",
        "name": "CMS Claims Drop",
        "source_type": "filesystem",
        "credentials_ref": "env:CMS_CONNECTOR_TOKEN",
        "schedule": {"mode": "manual"},
        "mapping": {
            "mapping_id": "claims-feed",
            "mapping_version": "v1",
            "feed_name": "claims_feed",
        },
        "config": {"path": "/imports/cms/claims.csv"},
    }


def _connector_definition() -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id="cms-claims-drop",
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id=KB_ID,
        credentials_ref="env:CMS_CONNECTOR_TOKEN",
        schedule=ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims-feed",
            mapping_version="v1",
            feed_name="claims_feed",
        ),
        config={"path": "/imports/cms/claims.csv"},
    )


def test_analyst_registers_connector_without_response_secret_ref() -> None:
    app, _service = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        response = client.post(BASE_URL, json=_connector_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["connector_id"] == "cms-claims-drop"
    assert body["knowledge_base_id"] == KB_ID
    assert body["credentials_display"] == "env:CMS...OKEN"
    assert "credentials_ref" not in body


def test_viewer_lists_connectors_and_cannot_register() -> None:
    app, service = _app_harness()
    _set_user(app, _user("viewer"))
    service.register_connector(KB_ID, _connector_definition())

    with TestClient(app) as client:
        list_response = client.get(BASE_URL)
        post_response = client.post(BASE_URL, json=_connector_payload())

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["connector_id"] == "cms-claims-drop"
    assert post_response.status_code == 403


def test_analyst_starts_sync_run_and_lists_empty_quarantine() -> None:
    app, _service = _app_harness()
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        created = client.post(BASE_URL, json=_connector_payload())
        run_response = client.post(
            f"{BASE_URL}/cms-claims-drop/sync-runs",
            json={"idempotency_key": "run-key-1"},
        )
        quarantine_response = client.get(f"{BASE_URL}/cms-claims-drop/quarantine")

    assert created.status_code == 200
    assert run_response.status_code == 200
    run = run_response.json()
    assert run["connector_id"] == "cms-claims-drop"
    assert run["knowledge_base_id"] == KB_ID
    assert run["status"] == "queued"
    assert run["idempotency_key"] == "run-key-1"
    assert quarantine_response.status_code == 200
    assert quarantine_response.json()["total"] == 0


def test_connector_routes_return_404_for_out_of_scope_kb() -> None:
    app, _service = _app_harness()
    _set_user(app, _user("viewer", knowledge_base_ids=["kb-other"]))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 404


def test_registering_an_unimplemented_source_type_returns_422_not_409() -> None:
    """Invalid input, not a conflict.

    `register_connector` raises ValueError for a genuine definition conflict,
    which maps to 409. If ConnectorValidationError were caught by that clause —
    or subclassed ValueError — an operator asking for an unbuilt source type
    would be told their connector already exists.
    """
    app, _service = _app_harness()
    _set_user(app, _user("analyst"))
    payload = {**_connector_payload(), "source_type": "http"}

    with TestClient(app) as client:
        response = client.post(BASE_URL, json=payload)

    assert response.status_code == 422
    assert "not implemented" in response.json()["detail"]
    assert "filesystem" in response.json()["detail"]


def test_registering_a_scheduled_connector_returns_422() -> None:
    app, _service = _app_harness()
    _set_user(app, _user("analyst"))
    payload = {**_connector_payload(), "schedule": {"mode": "cron", "expression": "0 3 * * *"}}

    with TestClient(app) as client:
        response = client.post(BASE_URL, json=payload)

    assert response.status_code == 422
    assert "not implemented" in response.json()["detail"]


def test_a_genuine_definition_conflict_still_returns_409() -> None:
    """The new 422 clause must not have swallowed the conflict case."""
    app, service = _app_harness()
    _set_user(app, _user("analyst"))
    service.register_connector(KB_ID, _connector_definition())
    conflicting = {**_connector_payload(), "name": "A Different Name"}

    with TestClient(app) as client:
        response = client.post(BASE_URL, json=conflicting)

    assert response.status_code == 409
