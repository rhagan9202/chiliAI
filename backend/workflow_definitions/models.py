from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, Field, computed_field

from shared.utils import utc_now

BUILT_IN_WORKFLOW_CAPABILITIES = frozenset(
    {
        "playbook.step",
        "rag.query",
        "analytics.peer_context",
        "evidence.checklist.generate",
        "case.note.draft",
        "human.approval",
    }
)
HUMAN_APPROVAL_CAPABILITIES = frozenset({"case.note.draft", "human.approval"})

WorkflowDefinitionStatus: TypeAlias = Literal["draft", "approved", "retired"]
WorkflowRunTargetType: TypeAlias = Literal["alert", "entity", "case", "knowledge_base"]
MetadataValue: TypeAlias = str | int | float | bool


class WorkflowFailureMode(StrEnum):
    FAIL_WORKFLOW = "fail_workflow"
    CONTINUE = "continue"
    REQUIRE_APPROVAL = "require_approval"


class WorkflowRetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1)


class WorkflowStepDefinition(BaseModel):
    step_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    input_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    output_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    condition: str | None = None
    retry_policy: WorkflowRetryPolicy | None = None
    requires_human_approval: bool = False
    on_failure: WorkflowFailureMode = WorkflowFailureMode.FAIL_WORKFLOW


class WorkflowDefinitionCreate(BaseModel):
    definition_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str | None = None
    domain_name: str | None = None
    allowed_capability_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    steps: list[WorkflowStepDefinition] = Field(
        default_factory=lambda: cast(list[WorkflowStepDefinition], [])
    )


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    domain_name: str | None = None
    allowed_capability_refs: list[str] | None = None
    steps: list[WorkflowStepDefinition] | None = None


class WorkflowDefinitionRunRequest(BaseModel):
    target_type: WorkflowRunTargetType
    target_id: str = Field(min_length=1)
    inputs: dict[str, MetadataValue] = Field(
        default_factory=lambda: cast(dict[str, MetadataValue], {})
    )
    idempotency_key: str | None = Field(default=None, min_length=1)


class WorkflowDefinitionValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=lambda: cast(list[str], []))
    warnings: list[str] = Field(default_factory=lambda: cast(list[str], []))


class WorkflowDefinition(BaseModel):
    definition_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    domain_name: str | None = None
    name: str = Field(min_length=1)
    description: str | None = None
    version: str = Field(min_length=1)
    status: WorkflowDefinitionStatus = "draft"
    allowed_capability_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    steps: list[WorkflowStepDefinition] = Field(
        default_factory=lambda: cast(list[WorkflowStepDefinition], [])
    )
    created_by: str = Field(min_length=1)
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    retired_at: datetime | None = None

    @computed_field
    @property
    def snapshot_id(self) -> str:
        return f"{self.knowledge_base_id}:{self.definition_id}:{self.version}"


class WorkflowDefinitionPage(BaseModel):
    items: list[WorkflowDefinition] = Field(
        default_factory=lambda: cast(list[WorkflowDefinition], [])
    )
    total_items: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


def validate_workflow_definition_payload(
    payload: WorkflowDefinitionCreate | WorkflowDefinitionUpdate,
) -> WorkflowDefinitionValidationResult:
    errors: list[str] = []
    allowed_refs = payload.allowed_capability_refs or []
    steps = payload.steps or []

    for capability_ref in allowed_refs:
        if capability_ref not in BUILT_IN_WORKFLOW_CAPABILITIES:
            errors.append(
                f"allowed_capability_refs contains unknown capability '{capability_ref}'."
            )

    step_ids = [step.step_id for step in steps]
    if len(step_ids) != len(set(step_ids)):
        errors.append("Workflow step ids must be unique.")

    allowed_ref_set = set(allowed_refs)
    for step in steps:
        if step.capability_ref not in BUILT_IN_WORKFLOW_CAPABILITIES:
            errors.append(
                f"Step '{step.step_id}' references unknown capability '{step.capability_ref}'."
            )
            continue
        if step.capability_ref not in allowed_ref_set:
            errors.append(
                f"Step '{step.step_id}' capability '{step.capability_ref}' "
                "is not allowed by this definition."
            )
        if (
            step.capability_ref in HUMAN_APPROVAL_CAPABILITIES
            and not step.requires_human_approval
        ):
            errors.append(
                f"Step '{step.step_id}' using capability '{step.capability_ref}' "
                "must require human approval."
            )

    return WorkflowDefinitionValidationResult(valid=not errors, errors=errors)


__all__ = [
    "BUILT_IN_WORKFLOW_CAPABILITIES",
    "HUMAN_APPROVAL_CAPABILITIES",
    "MetadataValue",
    "WorkflowDefinition",
    "WorkflowDefinitionCreate",
    "WorkflowDefinitionPage",
    "WorkflowDefinitionRunRequest",
    "WorkflowDefinitionStatus",
    "WorkflowDefinitionUpdate",
    "WorkflowDefinitionValidationResult",
    "WorkflowFailureMode",
    "WorkflowRetryPolicy",
    "WorkflowRunTargetType",
    "WorkflowStepDefinition",
    "validate_workflow_definition_payload",
]
