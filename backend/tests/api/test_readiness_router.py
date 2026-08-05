"""Tests for SAFE-CMS-018 knowledge-base readiness API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from capabilities.service import create_default_capability_registry_service
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncCounters,
)
from connectors.service import ConnectorService
from fastapi import FastAPI
from fastapi.testclient import TestClient
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from readiness.service import ReadinessService
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinitionCreate, WorkflowStepDefinition
from workflow_definitions.service import WorkflowDefinitionService

from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_readiness_service,
)
from api.middleware.auth import User, get_current_user

BASE_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
KB_ID = "kb-cms"
READINESS_URL = f"/knowledgebases/{KB_ID}/readiness"
KnowledgeBaseStatus = Literal["active", "building", "ready", "error", "archived"]


def _domain_config() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


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


def _knowledge_base(status: KnowledgeBaseStatus = "ready") -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID,
        name="CMS Fraud KB",
        description="Readiness API test KB",
        domain="medicare_fraud",
        status=status,
        document_count=3,
        entity_count=25,
        relationship_count=40,
        created_at=BASE_TIME,
    )


def _workflow_service() -> WorkflowDefinitionService:
    return WorkflowDefinitionService(
        InMemoryWorkflowDefinitionRepository(),
        InMemoryWorkflowRunStore(),
        AuditLogService(InMemoryAuditLogRepository()),
    )


def _app_harness(
    *,
    seed_ready: bool = True,
    kb_status: KnowledgeBaseStatus = "ready",
) -> tuple[FastAPI, InMemoryKnowledgeBaseRepository]:
    app = create_app()
    kb_repository = InMemoryKnowledgeBaseRepository()
    connector_service = ConnectorService(InMemoryConnectorRepository())
    workflow_service = _workflow_service()
    if seed_ready:
        kb_repository.create(_knowledge_base(status=kb_status))
        _seed_connector(connector_service)
        _seed_workflow(workflow_service)
    readiness_service = ReadinessService(
        knowledge_base_repository=kb_repository,
        connector_service=connector_service,
        workflow_definition_service=workflow_service,
        capability_registry=create_default_capability_registry_service(),
        active_domain_name="medicare_fraud",
    )
    app.dependency_overrides[get_domain_config] = _domain_config
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_readiness_service] = lambda: readiness_service
    return app, kb_repository


def _seed_connector(connector_service: ConnectorService) -> None:
    connector_service.register_connector(
        KB_ID,
        ConnectorDefinitionCreate(
            connector_id="cms-claims",
            name="CMS Claims",
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
        ),
    )
    run = connector_service.start_sync(
        knowledge_base_id=KB_ID,
        connector_id="cms-claims",
        requested_by="operator-1",
    )
    connector_service.complete_sync(
        run.run_id,
        counters=ConnectorSyncCounters(pulled=3, accepted=3, quarantined=0, failed=0),
        ingest_correlation_id="ingest-1",
        source_cursor="claims.csv:3",
    )


def _seed_workflow(workflow_service: WorkflowDefinitionService) -> None:
    workflow_service.create_draft(
        KB_ID,
        WorkflowDefinitionCreate(
            definition_id="daily-review",
            name="Daily Review",
            version="v1",
            domain_name="medicare_fraud",
            allowed_capability_refs=["rag.query"],
            steps=[
                WorkflowStepDefinition(
                    step_id="ask",
                    label="Ask",
                    capability_ref="rag.query",
                )
            ],
        ),
        actor_user_id="analyst-1",
        actor_email="analyst@example.test",
        actor_roles=["analyst"],
        correlation_id="corr-1",
    )


def test_viewer_reads_knowledge_base_readiness_without_connector_secrets() -> None:
    app, _repository = _app_harness()
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(READINESS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["knowledge_base"]["id"] == KB_ID
    assert body["active_domain_name"] == "medicare_fraud"
    assert body["components"]["connectors"]["details"]["completed_runs"] == 1
    assert "CMS_CONNECTOR_TOKEN" not in response.text
    assert "credentials_ref" not in response.text


def test_viewer_outside_kb_scope_gets_404() -> None:
    app, _repository = _app_harness()
    _set_user(app, _user("viewer", knowledge_base_ids=["kb-other"]))

    with TestClient(app) as client:
        response = client.get(READINESS_URL)

    assert response.status_code == 404


def test_readiness_returns_404_for_missing_kb() -> None:
    app, _repository = _app_harness(seed_ready=False)
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(READINESS_URL)

    assert response.status_code == 404
