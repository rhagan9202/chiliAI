from __future__ import annotations

from typing import Any

import pytest

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRunStatus
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEvent, AuditEventQuery
from auditlog.service import AuditLogService
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionRunRequest,
    WorkflowDefinitionUpdate,
    WorkflowStepDefinition,
)
from workflow_definitions.service import (
    WorkflowDefinitionConflictError,
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionService,
    WorkflowDefinitionValidationError,
)

ACTOR_KWARGS: dict[str, Any] = {
    "actor_user_id": "analyst-1",
    "actor_email": "analyst@example.test",
    "actor_roles": ["analyst"],
}

ADMIN_KWARGS: dict[str, Any] = {
    "actor_user_id": "admin-1",
    "actor_email": "admin@example.test",
    "actor_roles": ["admin"],
}


def _valid_create_payload() -> WorkflowDefinitionCreate:
    return WorkflowDefinitionCreate(
        definition_id="provider-review",
        domain_name="medicare_fraud",
        name="Provider review",
        version="v1",
        description="Review suspicious provider behavior.",
        allowed_capability_refs=["rag.query", "analytics.peer_context"],
        steps=[
            WorkflowStepDefinition(
                step_id="ask-rag",
                label="Ask RAG",
                capability_ref="rag.query",
            ),
            WorkflowStepDefinition(
                step_id="peer-context",
                label="Peer context",
                capability_ref="analytics.peer_context",
            ),
        ],
    )


def _service(
    *,
    repository: InMemoryWorkflowDefinitionRepository | None = None,
    run_store: InMemoryWorkflowRunStore | None = None,
    audit_repository: InMemoryAuditLogRepository | None = None,
) -> tuple[
    WorkflowDefinitionService,
    InMemoryWorkflowDefinitionRepository,
    InMemoryWorkflowRunStore,
    AuditLogService,
]:
    definition_repository = repository or InMemoryWorkflowDefinitionRepository()
    workflow_run_store = run_store or InMemoryWorkflowRunStore()
    audit_log_repository = audit_repository or InMemoryAuditLogRepository()
    audit_service = AuditLogService(audit_log_repository)
    return (
        WorkflowDefinitionService(
            definition_repository,
            workflow_run_store,
            audit_service,
            tenant_id="tenant-1",
        ),
        definition_repository,
        workflow_run_store,
        audit_service,
    )


def _audit_events(audit_service: AuditLogService) -> list[AuditEvent]:
    page = audit_service.list_events(
        AuditEventQuery(tenant_id="tenant-1", action_prefix="workflow_definition.")
    )
    return list(reversed(page.items))


def test_create_draft_rejects_unknown_capability_before_persistence() -> None:
    service, repository, _, _ = _service()
    payload = _valid_create_payload().model_copy(
        update={"allowed_capability_refs": ["unknown.capability"]}
    )

    with pytest.raises(WorkflowDefinitionValidationError):
        service.create_draft("kb-1", payload, **ACTOR_KWARGS)

    assert repository.list_definitions(knowledge_base_id="kb-1").items == []


def test_create_draft_returns_snapshot_id() -> None:
    service, _, _, _ = _service()
    payload = _valid_create_payload().model_copy(
        update={"definition_id": "provider-review-workflow"}
    )

    created = service.create_draft("kb-workflows", payload, **ACTOR_KWARGS)

    assert created.snapshot_id == "kb-workflows:provider-review-workflow:v1"


def test_update_draft_accepts_full_create_payload() -> None:
    service, _, _, _ = _service()
    created = service.create_draft("kb-1", _valid_create_payload(), **ACTOR_KWARGS)
    replacement = _valid_create_payload().model_copy(update={"name": "Full replacement"})

    updated = service.update_draft(
        "kb-1",
        created.definition_id,
        created.version,
        replacement,
        **ACTOR_KWARGS,
    )

    assert updated.name == "Full replacement"


def test_lifecycle_records_audit_events_in_order() -> None:
    service, _, _, audit_service = _service()

    created = service.create_draft("kb-1", _valid_create_payload(), **ACTOR_KWARGS)
    updated = service.update_draft(
        "kb-1",
        created.definition_id,
        created.version,
        WorkflowDefinitionUpdate(name="Provider review updated"),
        **ACTOR_KWARGS,
    )
    approved = service.approve_definition(
        "kb-1", updated.definition_id, updated.version, **ADMIN_KWARGS
    )
    retired = service.retire_definition(
        "kb-1", approved.definition_id, approved.version, **ADMIN_KWARGS
    )

    assert created.status == "draft"
    assert updated.name == "Provider review updated"
    assert approved.status == "approved"
    assert approved.approved_by == "admin-1"
    assert retired.status == "retired"
    events = _audit_events(audit_service)
    assert [event.action for event in events] == [
        "workflow_definition.created",
        "workflow_definition.updated",
        "workflow_definition.approved",
        "workflow_definition.retired",
    ]
    assert all(
        event.resource_type == "workflow_definition"
        and event.resource_id == "provider-review:v1"
        and event.knowledge_base_id == "kb-1"
        for event in events
    )


def test_retire_definition_is_idempotent_without_duplicate_audit_event() -> None:
    service, _, _, audit_service = _service()
    created = service.create_draft("kb-1", _valid_create_payload(), **ACTOR_KWARGS)
    approved = service.approve_definition(
        "kb-1", created.definition_id, created.version, **ADMIN_KWARGS
    )

    first = service.retire_definition(
        "kb-1", approved.definition_id, approved.version, **ADMIN_KWARGS
    )
    second = service.retire_definition(
        "kb-1", approved.definition_id, approved.version, **ADMIN_KWARGS
    )

    assert first.status == "retired"
    assert second.status == "retired"
    retire_events = [
        event
        for event in _audit_events(audit_service)
        if event.action == "workflow_definition.retired"
    ]
    assert len(retire_events) == 1


def test_update_rejects_approved_definitions() -> None:
    service, _, _, _ = _service()
    created = service.create_draft("kb-1", _valid_create_payload(), **ACTOR_KWARGS)
    service.approve_definition(
        "kb-1", created.definition_id, created.version, **ADMIN_KWARGS
    )

    with pytest.raises(WorkflowDefinitionConflictError):
        service.update_draft(
            "kb-1",
            created.definition_id,
            created.version,
            WorkflowDefinitionUpdate(name="Cannot update"),
            **ACTOR_KWARGS,
        )


def test_run_approved_definition_creates_queued_workflow_run_and_audit_event() -> None:
    service, _, run_store, audit_service = _service()
    created = service.create_draft("kb-1", _valid_create_payload(), **ACTOR_KWARGS)
    approved = service.approve_definition(
        "kb-1", created.definition_id, created.version, **ADMIN_KWARGS
    )

    run = service.run_definition(
        "kb-1",
        approved.definition_id,
        approved.version,
        WorkflowDefinitionRunRequest(
            target_type="alert",
            target_id="alert-123",
            idempotency_key="idem-123",
        ),
        **ACTOR_KWARGS,
    )

    persisted = run_store.get_run(run.workflow_id)
    assert persisted.status is WorkflowRunStatus.QUEUED
    assert persisted.trigger_event_type == "workflow_definition.requested"
    assert [step.step_name for step in persisted.steps] == ["ask-rag", "peer-context"]
    assert persisted.idempotency_key == "idem-123"
    assert persisted.metadata == {
        "definition_id": "provider-review",
        "definition_version": "v1",
        "definition_status": "approved",
        "target_type": "alert",
        "target_id": "alert-123",
        "approved_by": "admin-1",
    }
    run_requested_event = _audit_events(audit_service)[-1]
    assert run_requested_event.action == "workflow_definition.run_requested"
    assert run_requested_event.metadata == {
        "domain_name": "medicare_fraud",
        "definition_id": "provider-review",
        "version": "v1",
        "run_id": run.workflow_id,
        "target_type": "alert",
        "target_id": "alert-123",
    }


def test_run_draft_is_rejected() -> None:
    service, _, _, _ = _service()
    created = service.create_draft("kb-1", _valid_create_payload(), **ACTOR_KWARGS)

    with pytest.raises(WorkflowDefinitionConflictError):
        service.run_definition(
            "kb-1",
            created.definition_id,
            created.version,
            WorkflowDefinitionRunRequest(target_type="alert", target_id="alert-123"),
            **ACTOR_KWARGS,
        )


def test_missing_definition_raises_not_found() -> None:
    service, _, _, _ = _service()

    with pytest.raises(WorkflowDefinitionNotFoundError):
        service.get_definition("kb-1", "missing", "v1")
