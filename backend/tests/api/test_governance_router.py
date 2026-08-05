"""Tests for SAFE-CMS-020 governance API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.explainability.reviews import (
    ExplanationReviewService,
    InMemoryExplanationReviewRepository,
)
from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_explanation_review_service,
    get_knowledge_base_repository,
    get_playbook_repository,
    get_workflow_definition_repository,
)
from api.middleware.auth import User, get_current_user
from config.loader import load_config
from config.schema import AuthConfig, FraudPlaybookConfig
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookSnapshot
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinition, WorkflowStepDefinition

BASE_TIME = datetime(2026, 8, 5, 14, 30, tzinfo=timezone.utc)
KB_ID = "kb-governance"
BASE_URL = f"/knowledgebases/{KB_ID}/governance/report"


def test_viewer_can_fetch_governance_report_for_authorized_kb() -> None:
    app, playbooks, workflows = _app_harness()
    playbooks.upsert_snapshot(_playbook_snapshot("billing-review", "v1"))
    workflows.save_definition(_workflow_definition("provider-review", "v1"))
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_base_id"] == KB_ID
    assert body["domain_name"] == "medicare_fraud"
    assert body["release_ready"] is True
    assert body["feedback_trends"]["total_reviews"] == 0
    assert [
        (item["component_kind"], item["component_id"], item["version"], item["status"])
        for item in body["production_versions"]
    ] == [
        ("playbook", "billing-review", "v1", "published"),
        ("workflow_definition", "provider-review", "v1", "approved"),
    ]


def test_out_of_scope_kb_returns_404() -> None:
    app, _, _ = _app_harness()
    _set_user(app, _user("viewer", knowledge_base_ids=["other-kb"]))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 404


def test_missing_published_playbook_baseline_blocks_report() -> None:
    app, _, workflows = _app_harness()
    workflows.save_definition(_workflow_definition("provider-review", "v1"))
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["release_ready"] is False
    assert [
        (
            blocker["severity"],
            blocker["code"],
            blocker["resource_type"],
            blocker["resource_id"],
        )
        for blocker in body["release_blockers"]
    ] == [
        (
            "blocking",
            "missing_playbook_baseline",
            "playbook",
            KB_ID,
        )
    ]


def _app_harness() -> tuple[
    FastAPI,
    InMemoryPlaybookRepository,
    InMemoryWorkflowDefinitionRepository,
]:
    app = create_app()
    kb_repository = InMemoryKnowledgeBaseRepository()
    kb_repository.create(
        KnowledgeBase(
            id=KB_ID,
            name="Governance KB",
            description="Governance API test KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    playbooks = InMemoryPlaybookRepository()
    workflows = InMemoryWorkflowDefinitionRepository()
    reviews = ExplanationReviewService(InMemoryExplanationReviewRepository())

    app.dependency_overrides[get_domain_config] = lambda: load_config().model_copy(
        update={"auth": AuthConfig(enabled=True)}
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_playbook_repository] = lambda: playbooks
    app.dependency_overrides[get_workflow_definition_repository] = lambda: workflows
    app.dependency_overrides[get_explanation_review_service] = lambda: reviews
    return app, playbooks, workflows


def _set_user(app: FastAPI, user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _user(role: str, *, knowledge_base_ids: list[str] | None = None) -> User:
    return User(
        user_id=f"{role}-1",
        roles=[role],
        email=f"{role}-1@example.test",
        knowledge_base_ids=knowledge_base_ids if knowledge_base_ids is not None else [KB_ID],
    )


def _playbook_snapshot(playbook_id: str, version: str) -> PlaybookSnapshot:
    return PlaybookSnapshot(
        snapshot_id=f"{KB_ID}:medicare_fraud:{playbook_id}:{version}",
        knowledge_base_id=KB_ID,
        domain_name="medicare_fraud",
        playbook_id=playbook_id,
        version=version,
        definition=FraudPlaybookConfig(
            id=playbook_id,
            version=version,
            title="Billing review",
            status="published",
        ),
        source="api_publish",
        published_by="supervisor-1",
        published_at=BASE_TIME,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _workflow_definition(definition_id: str, version: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id=definition_id,
        knowledge_base_id=KB_ID,
        domain_name="medicare_fraud",
        name="Provider review",
        version=version,
        status="approved",
        allowed_capability_refs=["rag.query"],
        steps=[
            WorkflowStepDefinition(
                step_id="ask-rag",
                label="Ask RAG",
                capability_ref="rag.query",
            )
        ],
        created_by="analyst-1",
        approved_by="supervisor-1",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        approved_at=BASE_TIME,
    )
