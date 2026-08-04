"""Workflow definition application service."""

from __future__ import annotations

from collections.abc import Sequence

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from auditlog.models import AuditEventCreate, JsonSummary
from auditlog.service import AuditLogService
from shared.utils import generate_id, utc_now
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionPage,
    WorkflowDefinitionRunRequest,
    WorkflowDefinitionUpdate,
    validate_workflow_definition_payload,
)
from workflow_definitions.repository import WorkflowDefinitionRepository

__all__ = [
    "WorkflowDefinitionConflictError",
    "WorkflowDefinitionError",
    "WorkflowDefinitionNotFoundError",
    "WorkflowDefinitionService",
    "WorkflowDefinitionValidationError",
]


class WorkflowDefinitionError(Exception):
    """Base workflow definition service error."""


class WorkflowDefinitionNotFoundError(WorkflowDefinitionError):
    """Raised when a workflow definition snapshot cannot be found."""

    def __init__(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> None:
        super().__init__(
            "Workflow definition "
            f"{knowledge_base_id}:{definition_id}:{version} was not found."
        )
        self.knowledge_base_id = knowledge_base_id
        self.definition_id = definition_id
        self.version = version


class WorkflowDefinitionConflictError(WorkflowDefinitionError):
    """Raised when a lifecycle operation conflicts with current state."""


class WorkflowDefinitionValidationError(WorkflowDefinitionError):
    """Raised when a definition payload fails validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        super().__init__("Workflow definition payload failed validation.")
        self.errors = list(errors)


class WorkflowDefinitionService:
    """Coordinates workflow definition persistence, audit, and preview runs."""

    def __init__(
        self,
        repository: WorkflowDefinitionRepository,
        run_store: WorkflowRunStoreProtocol,
        audit_service: AuditLogService,
        *,
        tenant_id: str = "default",
    ) -> None:
        self._repository = repository
        self._run_store = run_store
        self._audit_service = audit_service
        self._tenant_id = tenant_id

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage:
        return self._repository.list_definitions(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )

    def get_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition:
        return self._get_required_definition(knowledge_base_id, definition_id, version)

    def create_draft(
        self,
        knowledge_base_id: str,
        payload: WorkflowDefinitionCreate,
        *,
        actor_user_id: str,
        actor_email: str | None = None,
        actor_roles: Sequence[str] = (),
    ) -> WorkflowDefinition:
        self._validate_payload(payload)
        now = utc_now()
        definition = WorkflowDefinition(
            definition_id=payload.definition_id,
            knowledge_base_id=knowledge_base_id,
            domain_name=payload.domain_name,
            name=payload.name,
            description=payload.description,
            version=payload.version,
            status="draft",
            allowed_capability_refs=list(payload.allowed_capability_refs),
            steps=[step.model_copy(deep=True) for step in payload.steps],
            created_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        try:
            saved = self._repository.save_definition(definition)
        except ValueError as exc:
            raise WorkflowDefinitionConflictError(str(exc)) from exc
        self._record_definition_audit(
            action="workflow_definition.created",
            definition=saved,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
        )
        return saved

    def update_draft(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        payload: WorkflowDefinitionCreate | WorkflowDefinitionUpdate,
        *,
        actor_user_id: str,
        actor_email: str | None = None,
        actor_roles: Sequence[str] = (),
    ) -> WorkflowDefinition:
        existing = self._get_required_definition(
            knowledge_base_id,
            definition_id,
            version,
        )
        if existing.status != "draft":
            raise WorkflowDefinitionConflictError(
                "Only draft workflow definitions can be updated."
            )
        candidate = self._apply_update(existing, payload)
        self._validate_definition(candidate)
        updated = self._repository.update_definition(candidate)
        self._record_definition_audit(
            action="workflow_definition.updated",
            definition=updated,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
        )
        return updated

    def approve_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        *,
        actor_user_id: str,
        actor_email: str | None = None,
        actor_roles: Sequence[str] = (),
    ) -> WorkflowDefinition:
        existing = self._get_required_definition(
            knowledge_base_id,
            definition_id,
            version,
        )
        if existing.status != "draft":
            raise WorkflowDefinitionConflictError(
                "Only draft workflow definitions can be approved."
            )
        now = utc_now()
        approved = existing.model_copy(
            update={
                "status": "approved",
                "approved_by": actor_user_id,
                "approved_at": now,
                "updated_at": now,
            },
            deep=True,
        )
        updated = self._repository.update_definition(approved)
        self._record_definition_audit(
            action="workflow_definition.approved",
            definition=updated,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
        )
        return updated

    def retire_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        *,
        actor_user_id: str,
        actor_email: str | None = None,
        actor_roles: Sequence[str] = (),
    ) -> WorkflowDefinition:
        existing = self._get_required_definition(
            knowledge_base_id,
            definition_id,
            version,
        )
        if existing.status == "retired":
            return existing
        if existing.status != "approved":
            raise WorkflowDefinitionConflictError(
                "Only approved workflow definitions can be retired."
            )
        now = utc_now()
        retired = existing.model_copy(
            update={
                "status": "retired",
                "retired_at": now,
                "updated_at": now,
            },
            deep=True,
        )
        updated = self._repository.update_definition(retired)
        self._record_definition_audit(
            action="workflow_definition.retired",
            definition=updated,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
        )
        return updated

    def run_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        request: WorkflowDefinitionRunRequest,
        *,
        actor_user_id: str,
        actor_email: str | None = None,
        actor_roles: Sequence[str] = (),
    ) -> WorkflowRun:
        definition = self._get_required_definition(
            knowledge_base_id,
            definition_id,
            version,
        )
        if definition.status != "approved":
            raise WorkflowDefinitionConflictError(
                "Only approved workflow definitions can be run."
            )
        run = WorkflowRun(
            workflow_id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            trigger_event_type="workflow_definition.requested",
            status=WorkflowRunStatus.QUEUED,
            steps=[
                WorkflowStepState(step_name=step.step_id) for step in definition.steps
            ],
            metadata={
                "definition_id": definition.definition_id,
                "definition_version": definition.version,
                "definition_status": definition.status,
                "target_type": request.target_type,
                "target_id": request.target_id,
                "approved_by": definition.approved_by or "",
            },
            idempotency_key=request.idempotency_key,
        )
        try:
            saved_run = self._run_store.save_run(run)
        except ValueError as exc:
            raise WorkflowDefinitionConflictError(str(exc)) from exc
        self._record_definition_audit(
            action="workflow_definition.run_requested",
            definition=definition,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
            metadata={
                "run_id": saved_run.workflow_id,
                "target_type": request.target_type,
                "target_id": request.target_id,
            },
        )
        return saved_run

    def _get_required_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition:
        definition = self._repository.get_definition(
            knowledge_base_id,
            definition_id,
            version,
        )
        if definition is None:
            raise WorkflowDefinitionNotFoundError(
                knowledge_base_id,
                definition_id,
                version,
            )
        return definition

    @staticmethod
    def _apply_update(
        existing: WorkflowDefinition,
        payload: WorkflowDefinitionCreate | WorkflowDefinitionUpdate,
    ) -> WorkflowDefinition:
        update = payload.model_dump(exclude_unset=True)
        update.pop("definition_id", None)
        update.pop("version", None)
        update["updated_at"] = utc_now()
        merged = existing.model_dump()
        merged.update(update)
        return WorkflowDefinition.model_validate(merged)

    @staticmethod
    def _validate_payload(payload: WorkflowDefinitionCreate) -> None:
        result = validate_workflow_definition_payload(payload)
        if not result.valid:
            raise WorkflowDefinitionValidationError(result.errors)

    @staticmethod
    def _validate_definition(definition: WorkflowDefinition) -> None:
        payload = WorkflowDefinitionCreate(
            definition_id=definition.definition_id,
            name=definition.name,
            version=definition.version,
            description=definition.description,
            domain_name=definition.domain_name,
            allowed_capability_refs=list(definition.allowed_capability_refs),
            steps=[step.model_copy(deep=True) for step in definition.steps],
        )
        WorkflowDefinitionService._validate_payload(payload)

    def _record_definition_audit(
        self,
        *,
        action: str,
        definition: WorkflowDefinition,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: Sequence[str],
        metadata: JsonSummary | None = None,
    ) -> None:
        audit_metadata: JsonSummary = {
            "domain_name": definition.domain_name,
            "definition_id": definition.definition_id,
            "version": definition.version,
        }
        if metadata is not None:
            audit_metadata.update(metadata)
        self._audit_service.record(
            AuditEventCreate(
                tenant_id=self._tenant_id,
                knowledge_base_id=definition.knowledge_base_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                actor_roles=list(actor_roles),
                action=action,
                resource_type="workflow_definition",
                resource_id=f"{definition.definition_id}:{definition.version}",
                correlation_id=self._audit_correlation_id(action, definition),
                metadata=audit_metadata,
            )
        )

    @staticmethod
    def _audit_correlation_id(action: str, definition: WorkflowDefinition) -> str:
        snapshot_id = (
            f"{definition.knowledge_base_id}:"
            f"{definition.definition_id}:"
            f"{definition.version}"
        )
        return f"{action}:{snapshot_id}"
