"""Tests for KB-scoped capability registry API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config, get_knowledge_base_repository
from api.middleware.auth import User, get_current_user
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import KnowledgeBase

BASE_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
KB_ID = "kb-capabilities"
BASE_URL = f"/knowledgebases/{KB_ID}/capabilities"


def _domain_config() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _knowledge_base_repository() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id=KB_ID,
            name="Capability KB",
            description="Capability registry API test KB",
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


def _app_harness() -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_domain_config] = _domain_config
    app.dependency_overrides[get_knowledge_base_repository] = _knowledge_base_repository
    return app


def test_viewer_can_browse_kb_capabilities() -> None:
    app = _app_harness()
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["items"][0]["capability_id"] == "analytics.peer_context"
    assert body["items"][0]["input_schema"]["type"] == "object"
    assert body["items"][0]["permission"]["required_roles"] == ["viewer"]


def test_capability_browse_filters_by_role_and_side_effect_class() -> None:
    app = _app_harness()
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(
            BASE_URL,
            params={"role": "viewer", "side_effect_class": "read"},
        )

    assert response.status_code == 200
    assert {item["capability_id"] for item in response.json()["items"]} == {
        "analytics.peer_context",
        "connector.sync.status",
        "rag.query",
    }


def test_capability_browse_returns_404_for_out_of_scope_kb() -> None:
    app = _app_harness()
    _set_user(app, _user("viewer", knowledge_base_ids=["kb-other"]))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 404


def test_the_browse_api_says_which_capabilities_can_actually_run() -> None:
    """A registered capability is not necessarily a runnable one.

    An author picking from this list needs to know before authoring a workflow,
    not after running one and reading `capability_not_executable`.
    """
    from capabilities.executors import clear_executors, register_executor

    clear_executors()
    try:
        register_executor("connector.sync.status", lambda payload, context: {})
        app = _app_harness()
        _set_user(app, _user("analyst"))

        with TestClient(app) as client:
            response = client.get(BASE_URL)

        items = {item["capability_id"]: item["executable"] for item in response.json()["items"]}
        assert items["connector.sync.status"] is True
        assert items["evidence.checklist.generate"] is False
    finally:
        clear_executors()
