from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from collections.abc import Collection
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, Field, computed_field

from capabilities.registry import create_default_capability_registry
from shared.utils import utc_now
from workflow_definitions.conditions import ConditionSyntaxError, parse_condition

def _builtin_capability_refs() -> frozenset[str]:
    """Capability ids a definition may reference when no registry is supplied.

    Derived from the registry rather than written out, because the two had
    drifted: this set listed `playbook.step` and `human.approval`, which have
    no manifest, while omitting `connector.sync.status`, which does. The router
    always passes the real registry, so validation was *stricter* in production
    than in the fallback — a definition could pass a unit test using
    `human.approval` and then be rejected with "unknown capability" by the API.
    """

    return frozenset(
        manifest.capability_id
        for manifest in create_default_capability_registry().list()
    )


BUILT_IN_WORKFLOW_CAPABILITIES = _builtin_capability_refs()
# Capabilities that may only appear in a step which requires human approval.
# `case.note.draft` writes analyst-visible narrative on a case; drafting one
# unsupervised is the thing the gate exists to prevent.
HUMAN_APPROVAL_CAPABILITIES = frozenset({"case.note.draft"})

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
    steps: list[WorkflowStepDefinition] = Field(min_length=1)


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    domain_name: str | None = None
    allowed_capability_refs: list[str] | None = None
    steps: list[WorkflowStepDefinition] | None = Field(default=None, min_length=1)


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
    steps: list[WorkflowStepDefinition] = Field(min_length=1)
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
    *,
    registered_capability_refs: Collection[str] | None = None,
) -> WorkflowDefinitionValidationResult:
    errors: list[str] = []
    allowed_refs = payload.allowed_capability_refs or []
    steps = payload.steps or []
    capability_refs = (
        BUILT_IN_WORKFLOW_CAPABILITIES
        if registered_capability_refs is None
        else frozenset(registered_capability_refs)
    )

    if isinstance(payload, WorkflowDefinitionCreate) and not steps:
        errors.append("Workflow definition requires at least one step.")
    if isinstance(payload, WorkflowDefinitionUpdate) and payload.steps is not None and not steps:
        errors.append("Workflow definition requires at least one step.")

    for capability_ref in allowed_refs:
        if capability_ref not in capability_refs:
            errors.append(
                f"allowed_capability_refs contains unknown capability '{capability_ref}'."
            )

    step_ids = [step.step_id for step in steps]
    if len(step_ids) != len(set(step_ids)):
        errors.append("Workflow step ids must be unique.")

    allowed_ref_set = set(allowed_refs)
    for step in steps:
        if step.capability_ref not in capability_refs:
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

    known_step_ids = set(step_ids)
    for step in steps:
        if step.condition is None:
            continue
        try:
            parsed = parse_condition(step.condition)
        except ConditionSyntaxError as exc:
            # Rejected on create rather than at run time: an unparseable
            # condition would otherwise fail every execution of the workflow,
            # long after whoever wrote it has moved on.
            errors.append(f"Step '{step.step_id}' has an invalid condition: {exc}")
            continue
        if parsed.step_id not in known_step_ids:
            errors.append(
                f"Step '{step.step_id}' condition references unknown step "
                f"'{parsed.step_id}'."
            )
        elif step_ids.index(parsed.step_id) >= step_ids.index(step.step_id):
            # A condition can only read outputs that already exist. Referring
            # forward always evaluates false, so the step would silently never
            # run — the most expensive kind of authoring mistake to diagnose.
            errors.append(
                f"Step '{step.step_id}' condition references step "
                f"'{parsed.step_id}', which does not run before it."
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
