from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from capabilities.service import create_default_capability_registry_service
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncCounters,
)
from connectors.service import ConnectorService
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from readiness.service import ReadinessService
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinitionCreate, WorkflowStepDefinition
from workflow_definitions.service import WorkflowDefinitionService

BASE_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
KnowledgeBaseStatus = Literal["active", "building", "ready", "error", "archived"]


def _kb(status: KnowledgeBaseStatus = "ready") -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-cms",
        name="CMS Fraud KB",
        description="Readiness test KB",
        domain="medicare_fraud",
        status=status,
        document_count=3,
        entity_count=25,
        relationship_count=40,
        created_at=BASE_TIME,
    )


def _service() -> tuple[
    ReadinessService,
    ConnectorService,
    WorkflowDefinitionService,
    InMemoryKnowledgeBaseRepository,
]:
    kb_repository = InMemoryKnowledgeBaseRepository()
    connector_service = ConnectorService(InMemoryConnectorRepository())
    workflow_service = WorkflowDefinitionService(
        InMemoryWorkflowDefinitionRepository(),
        InMemoryWorkflowRunStore(),
        AuditLogService(InMemoryAuditLogRepository()),
    )
    return (
        ReadinessService(
            knowledge_base_repository=kb_repository,
            connector_service=connector_service,
            workflow_definition_service=workflow_service,
            capability_registry=create_default_capability_registry_service(),
            active_domain_name="medicare_fraud",
        ),
        connector_service,
        workflow_service,
        kb_repository,
    )


def test_readiness_is_ready_when_kb_connectors_workflows_and_capabilities_are_ready() -> None:
    readiness_service, connector_service, workflow_service, kb_repository = _service()
    kb_repository.create(_kb())
    connector_service.register_connector(
        "kb-cms",
        ConnectorDefinitionCreate(
            connector_id="cms-claims",
            name="CMS Claims",
            source_type="filesystem",
            knowledge_base_id="kb-cms",
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
        knowledge_base_id="kb-cms",
        connector_id="cms-claims",
        requested_by="operator-1",
    )
    connector_service.complete_sync(
        run.run_id,
        counters=ConnectorSyncCounters(pulled=3, accepted=3, quarantined=0, failed=0),
        ingest_correlation_id="ingest-1",
        source_cursor="claims.csv:3",
    )
    workflow_service.create_draft(
        "kb-cms",
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

    readiness = readiness_service.get_readiness("kb-cms")

    assert readiness.ready is True
    assert readiness.knowledge_base.id == "kb-cms"
    assert readiness.active_domain_name == "medicare_fraud"
    assert readiness.components["knowledge_base"].status == "ready"
    assert readiness.components["connectors"].status == "ready"
    assert readiness.components["workflows"].status == "ready"
    assert readiness.components["capabilities"].status == "ready"
    assert readiness.blockers == []
    assert readiness.components["connectors"].details["completed_runs"] == 1


def test_readiness_reports_blockers_for_building_kb_no_connectors_and_no_workflows() -> None:
    readiness_service, _connector_service, _workflow_service, kb_repository = _service()
    kb_repository.create(_kb(status="building"))

    readiness = readiness_service.get_readiness("kb-cms")

    assert readiness.ready is False
    assert {blocker.component for blocker in readiness.blockers} == {
        "knowledge_base",
        "connectors",
        "workflows",
    }
    assert readiness.components["knowledge_base"].status == "blocked"
    assert readiness.components["connectors"].status == "blocked"
    assert readiness.components["workflows"].status == "blocked"
    available_count = cast(
        int,
        readiness.components["capabilities"].details["available_count"],
    )
    assert available_count > 0
