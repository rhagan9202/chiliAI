# SAFE-CMS-014 Workflow Definitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build KB-scoped, versioned workflow definitions that analysts can draft and run after admin approval, with validation, audit events, durable persistence, and preview runs through the existing workflow run API.

**Architecture:** Add a new `backend/workflow_definitions/` package for models, repository protocols, stores, and service logic. Add a KB-scoped FastAPI router under `/knowledgebases/{knowledge_base_id}/workflow-definitions`, then wire it through existing dependency, RBAC, audit, OpenAPI, and migration patterns without changing the existing `/workflows` run-status API.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Alembic, Postgres JSONB, existing `WorkflowRunStoreProtocol`, existing `AuditLogService`, pytest, Ruff, Pyright, OpenAPI export, openapi-typescript.

---

## Implementation Status

- Completed in prior SAFE-CMS-014 passes: Tasks 1 through 6, including workflow-definition models, service lifecycle, KB-scoped API, run idempotency, Postgres persistence, generated contracts, and focused review fixes.
- Verification evidence: SAFE-CMS-014 implementation commits `08555ed` through `6216c2e`; the full surge closeout was merged to `origin/prod` at `271f305` on 2026-08-05.
- Remaining work: none; this plan is reconciled to the current `prod` state.

---

## Scope Reference

Design spec: `docs/superpowers/specs/2026-08-04-safe-cms-014-workflow-definitions-design.md`

Runway ADR: `docs/superpowers/specs/2026-08-04-safe-cms-pi4-playbooks-workflows-adr.md`

Current branch context: implemented on SAFE-CMS-014 feature commits and reconciled from `prod`.

## File Structure

- Create: `backend/workflow_definitions/models.py` for definition, step, validation, run request, page, and status models.
- Create: `backend/workflow_definitions/repository.py` for the repository protocol.
- Create: `backend/workflow_definitions/service.py` for validation, lifecycle transitions, audit event creation, and preview run creation.
- Create: `backend/workflow_definitions/adapters/in_memory.py` for tests and local development.
- Create: `backend/workflow_definitions/adapters/postgres.py` for durable persistence.
- Create: `backend/workflow_definitions/adapters/__init__.py` and `backend/workflow_definitions/__init__.py` for module exports.
- Create: `backend/api/routers/workflow_definitions.py` for KB-scoped HTTP routes.
- Modify: `backend/api/contracts.py` for request/response models.
- Modify: `backend/api/dependencies.py` for repository and service factories plus config-swap state.
- Modify: `backend/api/app.py` for router import and registration.
- Create: `backend/database/migrations/versions/0021_workflow_definition_snapshots.py`.
- Modify: `backend/database/migrations/snapshots/head.sql` after migration replay.
- Modify generated contracts: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts`.
- Create tests:
  - `backend/tests/workflow_definitions/test_models.py`
  - `backend/tests/workflow_definitions/test_in_memory.py`
  - `backend/tests/workflow_definitions/test_service.py`
  - `backend/tests/workflow_definitions/test_postgres.py`
  - `backend/tests/api/test_workflow_definitions_router.py`
  - `backend/tests/database/test_workflow_definitions_migration.py`

## Shared Test Fixtures

Use these helpers in new test files where useful:

```python
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from api.middleware.auth import User
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionRunRequest,
    WorkflowStepDefinition,
)
from workflow_definitions.service import WorkflowDefinitionService


def workflow_step(
    step_id: str = "gather-peer-context",
    capability_ref: str = "analytics.peer_context",
) -> WorkflowStepDefinition:
    return WorkflowStepDefinition(
        step_id=step_id,
        label="Gather peer context",
        capability_ref=capability_ref,
        input_refs=["alert.provider_npi"],
        output_refs=["peer_context"],
    )


def create_payload() -> WorkflowDefinitionCreate:
    return WorkflowDefinitionCreate(
        definition_id="provider-review-workflow",
        name="Provider review workflow",
        description="Review provider outlier alerts.",
        version="v1",
        allowed_capability_refs=["analytics.peer_context"],
        steps=[workflow_step()],
    )


def analyst_user() -> User:
    return SimpleNamespace(
        user_id="analyst-1",
        roles=["analyst"],
        email="analyst-1@example.com",
        knowledge_base_ids=["kb-workflows"],
    )


def admin_user() -> User:
    return SimpleNamespace(
        user_id="admin-1",
        roles=["admin"],
        email="admin-1@example.com",
        knowledge_base_ids=["kb-workflows"],
    )


def service_with_memory() -> tuple[
    InMemoryWorkflowDefinitionRepository,
    InMemoryWorkflowRunStore,
    WorkflowDefinitionService,
]:
    repository = InMemoryWorkflowDefinitionRepository()
    run_store = InMemoryWorkflowRunStore()
    service = WorkflowDefinitionService(
        repository=repository,
        run_store=run_store,
        audit_service=None,
    )
    return repository, run_store, service


def run_request() -> WorkflowDefinitionRunRequest:
    return WorkflowDefinitionRunRequest(
        target_type="alert",
        target_id="alert-1",
        inputs={"note": "review current alert"},
        idempotency_key="run-provider-review-alert-1",
    )
```

## Task 1: Models and Validation

**Files:**
- Create: `backend/workflow_definitions/models.py`
- Create: `backend/workflow_definitions/__init__.py`
- Create: `backend/tests/workflow_definitions/test_models.py`

- [x] **Step 1: Write RED model validation tests**

Create `backend/tests/workflow_definitions/test_models.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workflow_definitions.models import (
    BUILT_IN_WORKFLOW_CAPABILITIES,
    WorkflowDefinitionCreate,
    WorkflowFailureMode,
    WorkflowStepDefinition,
    validate_workflow_definition_payload,
)


def test_definition_validation_rejects_unknown_step_capability() -> None:
    payload = WorkflowDefinitionCreate(
        definition_id="provider-review-workflow",
        name="Provider review workflow",
        version="v1",
        allowed_capability_refs=["unknown.capability"],
        steps=[
            WorkflowStepDefinition(
                step_id="unknown-step",
                label="Unknown step",
                capability_ref="unknown.capability",
            )
        ],
    )

    result = validate_workflow_definition_payload(payload)

    assert result.valid is False
    assert result.errors == [
        "allowed_capability_refs contains unknown capability 'unknown.capability'.",
        "Step 'unknown-step' references unknown capability 'unknown.capability'.",
    ]


def test_definition_validation_rejects_step_capability_not_allowed() -> None:
    payload = WorkflowDefinitionCreate(
        definition_id="provider-review-workflow",
        name="Provider review workflow",
        version="v1",
        allowed_capability_refs=["rag.query"],
        steps=[
            WorkflowStepDefinition(
                step_id="peer-context",
                label="Peer context",
                capability_ref="analytics.peer_context",
            )
        ],
    )

    result = validate_workflow_definition_payload(payload)

    assert result.valid is False
    assert result.errors == [
        "Step 'peer-context' capability 'analytics.peer_context' is not allowed by this definition."
    ]


def test_step_ids_must_be_unique() -> None:
    payload = WorkflowDefinitionCreate(
        definition_id="provider-review-workflow",
        name="Provider review workflow",
        version="v1",
        allowed_capability_refs=["rag.query"],
        steps=[
            WorkflowStepDefinition(step_id="ask-rag", label="Ask RAG", capability_ref="rag.query"),
            WorkflowStepDefinition(step_id="ask-rag", label="Ask RAG again", capability_ref="rag.query"),
        ],
    )

    result = validate_workflow_definition_payload(payload)

    assert result.valid is False
    assert result.errors == ["Workflow step ids must be unique."]


def test_human_or_case_draft_steps_force_human_approval() -> None:
    payload = WorkflowDefinitionCreate(
        definition_id="provider-review-workflow",
        name="Provider review workflow",
        version="v1",
        allowed_capability_refs=["case.note.draft"],
        steps=[
            WorkflowStepDefinition(
                step_id="draft-note",
                label="Draft case note",
                capability_ref="case.note.draft",
                requires_human_approval=False,
            )
        ],
    )

    result = validate_workflow_definition_payload(payload)

    assert result.valid is False
    assert result.errors == [
        "Step 'draft-note' using capability 'case.note.draft' must require human approval."
    ]


def test_retry_policy_requires_positive_attempts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        WorkflowStepDefinition(
            step_id="peer-context",
            label="Peer context",
            capability_ref="analytics.peer_context",
            retry_policy={"max_attempts": 0},
        )


def test_builtin_capability_catalog_is_intentionally_small() -> None:
    assert BUILT_IN_WORKFLOW_CAPABILITIES == frozenset(
        {
            "playbook.step",
            "rag.query",
            "analytics.peer_context",
            "evidence.checklist.generate",
            "case.note.draft",
            "human.approval",
        }
    )
    assert WorkflowFailureMode.FAIL_WORKFLOW == "fail_workflow"
```

- [x] **Step 2: Run RED tests**

Run:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_models.py -q
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'workflow_definitions'`.

- [x] **Step 3: Add model implementation**

Create `backend/workflow_definitions/models.py`:

```python
"""Workflow definition models for SAFE-CMS-014."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now

BUILT_IN_WORKFLOW_CAPABILITIES: frozenset[str] = frozenset(
    {
        "playbook.step",
        "rag.query",
        "analytics.peer_context",
        "evidence.checklist.generate",
        "case.note.draft",
        "human.approval",
    }
)
HUMAN_APPROVAL_CAPABILITIES: frozenset[str] = frozenset(
    {"case.note.draft", "human.approval"}
)

WorkflowDefinitionStatus = Literal["draft", "approved", "retired"]
WorkflowRunTargetType = Literal["alert", "entity", "case", "knowledge_base"]
MetadataValue = str | int | float | bool


class WorkflowFailureMode(StrEnum):
    """Failure behavior for a user-authored workflow step."""

    FAIL_WORKFLOW = "fail_workflow"
    CONTINUE = "continue"
    REQUIRE_APPROVAL = "require_approval"


class WorkflowRetryPolicy(BaseModel):
    """Retry policy carried on a workflow step definition."""

    max_attempts: int = Field(default=1, ge=1)


class WorkflowStepDefinition(BaseModel):
    """One authored workflow definition step."""

    step_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    capability_ref: str = Field(min_length=1, max_length=128)
    input_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    output_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    condition: str | None = Field(default=None, max_length=500)
    retry_policy: WorkflowRetryPolicy | None = None
    requires_human_approval: bool = False
    on_failure: WorkflowFailureMode = WorkflowFailureMode.FAIL_WORKFLOW


class WorkflowDefinitionCreate(BaseModel):
    """Payload for creating a draft workflow definition snapshot."""

    definition_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    version: str = Field(min_length=1, max_length=128)
    allowed_capability_refs: list[str] = Field(
        default_factory=lambda: cast(list[str], []), max_length=50
    )
    steps: list[WorkflowStepDefinition] = Field(
        default_factory=lambda: cast(list[WorkflowStepDefinition], []),
        min_length=1,
        max_length=100,
    )


class WorkflowDefinitionUpdate(BaseModel):
    """Payload for updating a draft workflow definition snapshot."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    allowed_capability_refs: list[str] | None = Field(default=None, max_length=50)
    steps: list[WorkflowStepDefinition] | None = Field(
        default=None, min_length=1, max_length=100
    )


class WorkflowDefinitionRunRequest(BaseModel):
    """Request to create a preview workflow run from an approved definition."""

    target_type: WorkflowRunTargetType
    target_id: str = Field(min_length=1, max_length=256)
    inputs: dict[str, MetadataValue] = Field(
        default_factory=lambda: cast(dict[str, MetadataValue], {})
    )
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)


class WorkflowDefinitionValidationResult(BaseModel):
    """Normalized definition validation result."""

    valid: bool
    errors: list[str] = Field(default_factory=lambda: cast(list[str], []))
    warnings: list[str] = Field(default_factory=lambda: cast(list[str], []))


class WorkflowDefinition(BaseModel):
    """Versioned user-authored workflow definition snapshot."""

    snapshot_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    domain_name: str = Field(min_length=1)
    definition_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    version: str = Field(min_length=1)
    status: WorkflowDefinitionStatus = "draft"
    allowed_capability_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    steps: list[WorkflowStepDefinition] = Field(
        default_factory=lambda: cast(list[WorkflowStepDefinition], []), min_length=1
    )
    created_by: str = Field(min_length=1)
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    retired_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_definition(self) -> WorkflowDefinition:
        result = validate_workflow_definition_payload(self)
        if not result.valid:
            raise ValueError("; ".join(result.errors))
        return self


class WorkflowDefinitionPage(BaseModel):
    """One page of workflow definitions."""

    items: list[WorkflowDefinition] = Field(
        default_factory=lambda: cast(list[WorkflowDefinition], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


def validate_workflow_definition_payload(
    payload: WorkflowDefinition | WorkflowDefinitionCreate | WorkflowDefinitionUpdate,
) -> WorkflowDefinitionValidationResult:
    """Validate authored workflow shape before persistence."""

    errors: list[str] = []
    allowed = list(payload.allowed_capability_refs or [])
    steps = list(payload.steps or [])

    for capability_ref in allowed:
        if capability_ref not in BUILT_IN_WORKFLOW_CAPABILITIES:
            errors.append(
                f"allowed_capability_refs contains unknown capability '{capability_ref}'."
            )

    step_ids = [step.step_id for step in steps]
    if len(set(step_ids)) != len(step_ids):
        errors.append("Workflow step ids must be unique.")

    allowed_set = set(allowed)
    for step in steps:
        if step.capability_ref not in BUILT_IN_WORKFLOW_CAPABILITIES:
            errors.append(
                f"Step '{step.step_id}' references unknown capability '{step.capability_ref}'."
            )
            continue
        if step.capability_ref not in allowed_set:
            errors.append(
                f"Step '{step.step_id}' capability '{step.capability_ref}' is not allowed by this definition."
            )
        if (
            step.capability_ref in HUMAN_APPROVAL_CAPABILITIES
            and not step.requires_human_approval
        ):
            errors.append(
                f"Step '{step.step_id}' using capability '{step.capability_ref}' must require human approval."
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
```

Create `backend/workflow_definitions/__init__.py`:

```python
"""Workflow definition service boundary."""

from __future__ import annotations

from workflow_definitions.models import (
    BUILT_IN_WORKFLOW_CAPABILITIES,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionPage,
    WorkflowDefinitionRunRequest,
    WorkflowDefinitionStatus,
    WorkflowDefinitionUpdate,
    WorkflowStepDefinition,
)

__all__ = [
    "BUILT_IN_WORKFLOW_CAPABILITIES",
    "WorkflowDefinition",
    "WorkflowDefinitionCreate",
    "WorkflowDefinitionPage",
    "WorkflowDefinitionRunRequest",
    "WorkflowDefinitionStatus",
    "WorkflowDefinitionUpdate",
    "WorkflowStepDefinition",
]
```

- [x] **Step 4: Run GREEN model tests**

Run:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_models.py -q
```

Expected: `6 passed`.

- [x] **Step 5: Commit Task 1**

Run:

```bash
git add backend/workflow_definitions/__init__.py backend/workflow_definitions/models.py backend/tests/workflow_definitions/test_models.py
git commit -m "Add SAFE-CMS-014 workflow definition models"
```

Expected: commit created with only these three files.

## Task 2: In-Memory Repository and Service Lifecycle

**Files:**
- Create: `backend/workflow_definitions/repository.py`
- Create: `backend/workflow_definitions/adapters/__init__.py`
- Create: `backend/workflow_definitions/adapters/in_memory.py`
- Create: `backend/workflow_definitions/service.py`
- Create: `backend/tests/workflow_definitions/test_in_memory.py`
- Create: `backend/tests/workflow_definitions/test_service.py`
- Modify: `backend/workflow_definitions/__init__.py`

- [x] **Step 1: Write RED repository tests**

Create `backend/tests/workflow_definitions/test_in_memory.py`:

```python
from __future__ import annotations

from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinition, WorkflowStepDefinition


def _definition(
    *,
    knowledge_base_id: str = "kb-workflows",
    definition_id: str = "provider-review-workflow",
    version: str = "v1",
    status: str = "draft",
) -> WorkflowDefinition:
    return WorkflowDefinition(
        snapshot_id=f"{knowledge_base_id}:{definition_id}:{version}",
        knowledge_base_id=knowledge_base_id,
        domain_name="medicare_fraud",
        definition_id=definition_id,
        name="Provider review workflow",
        version=version,
        status=status,
        allowed_capability_refs=["analytics.peer_context"],
        steps=[
            WorkflowStepDefinition(
                step_id="peer-context",
                label="Peer context",
                capability_ref="analytics.peer_context",
            )
        ],
        created_by="analyst-1",
    )


def test_save_and_get_return_deep_copies() -> None:
    repository = InMemoryWorkflowDefinitionRepository()
    original = _definition()

    stored = repository.save_definition(original)
    stored.name = "mutated"
    original.name = "mutated original"

    found = repository.get_definition(
        knowledge_base_id="kb-workflows",
        definition_id="provider-review-workflow",
        version="v1",
    )

    assert found is not None
    assert found.name == "Provider review workflow"


def test_list_filters_by_knowledge_base_and_sorts_by_key() -> None:
    repository = InMemoryWorkflowDefinitionRepository()
    repository.save_definition(_definition(definition_id="z-workflow", version="v2"))
    repository.save_definition(_definition(definition_id="a-workflow", version="v1"))
    repository.save_definition(
        _definition(knowledge_base_id="kb-other", definition_id="other", version="v1")
    )

    page = repository.list_definitions(
        knowledge_base_id="kb-workflows",
        limit=1,
        offset=1,
    )

    assert page.total == 2
    assert [(item.definition_id, item.version) for item in page.items] == [
        ("z-workflow", "v2")
    ]


def test_update_definition_replaces_existing_snapshot() -> None:
    repository = InMemoryWorkflowDefinitionRepository()
    repository.save_definition(_definition())
    updated = _definition()
    updated.name = "Updated provider workflow"

    stored = repository.update_definition(updated)
    found = repository.get_definition(
        knowledge_base_id="kb-workflows",
        definition_id="provider-review-workflow",
        version="v1",
    )

    assert stored.name == "Updated provider workflow"
    assert found is not None
    assert found.name == "Updated provider workflow"
```

- [x] **Step 2: Write RED service tests**

Create `backend/tests/workflow_definitions/test_service.py`:

```python
from __future__ import annotations

import pytest

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEventQuery
from auditlog.service import AuditLogService
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionRunRequest,
    WorkflowStepDefinition,
)
from workflow_definitions.service import (
    WorkflowDefinitionConflictError,
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionService,
    WorkflowDefinitionValidationError,
)


def _payload(
    *,
    capability_ref: str = "analytics.peer_context",
    allowed_capability_refs: list[str] | None = None,
) -> WorkflowDefinitionCreate:
    return WorkflowDefinitionCreate(
        definition_id="provider-review-workflow",
        name="Provider review workflow",
        description="Review provider outlier alerts.",
        version="v1",
        allowed_capability_refs=allowed_capability_refs or [capability_ref],
        steps=[
            WorkflowStepDefinition(
                step_id="peer-context",
                label="Peer context",
                capability_ref=capability_ref,
                input_refs=["alert.provider_npi"],
                output_refs=["peer_context"],
            )
        ],
    )


def _service() -> tuple[
    InMemoryWorkflowDefinitionRepository,
    InMemoryWorkflowRunStore,
    AuditLogService,
    WorkflowDefinitionService,
]:
    repository = InMemoryWorkflowDefinitionRepository()
    run_store = InMemoryWorkflowRunStore()
    audit = AuditLogService(InMemoryAuditLogRepository())
    service = WorkflowDefinitionService(
        repository=repository,
        run_store=run_store,
        audit_service=audit,
    )
    return repository, run_store, audit, service


def test_create_draft_rejects_unknown_capability_before_persistence() -> None:
    repository, _, _, service = _service()

    with pytest.raises(
        WorkflowDefinitionValidationError,
        match="unknown capability 'unknown.capability'",
    ):
        service.create_draft(
            knowledge_base_id="kb-workflows",
            domain_name="medicare_fraud",
            payload=_payload(capability_ref="unknown.capability"),
            actor_user_id="analyst-1",
            actor_email="analyst-1@example.com",
            actor_roles=["analyst"],
            correlation_id="corr-1",
        )

    assert repository.list_definitions(knowledge_base_id="kb-workflows").total == 0


def test_create_update_approve_retire_lifecycle_records_audit_events() -> None:
    _, _, audit, service = _service()

    draft = service.create_draft(
        knowledge_base_id="kb-workflows",
        domain_name="medicare_fraud",
        payload=_payload(),
        actor_user_id="analyst-1",
        actor_email="analyst-1@example.com",
        actor_roles=["analyst"],
        correlation_id="corr-create",
    )
    updated = service.update_draft(
        knowledge_base_id="kb-workflows",
        definition_id=draft.definition_id,
        version=draft.version,
        payload=_payload().model_copy(update={"name": "Updated workflow"}),
        actor_user_id="analyst-1",
        actor_email="analyst-1@example.com",
        actor_roles=["analyst"],
        correlation_id="corr-update",
    )
    approved = service.approve_definition(
        knowledge_base_id="kb-workflows",
        definition_id=draft.definition_id,
        version=draft.version,
        actor_user_id="admin-1",
        actor_email="admin-1@example.com",
        actor_roles=["admin"],
        correlation_id="corr-approve",
    )
    retired = service.retire_definition(
        knowledge_base_id="kb-workflows",
        definition_id=draft.definition_id,
        version=draft.version,
        actor_user_id="admin-1",
        actor_email="admin-1@example.com",
        actor_roles=["admin"],
        correlation_id="corr-retire",
    )

    assert updated.name == "Updated workflow"
    assert approved.status == "approved"
    assert approved.approved_by == "admin-1"
    assert retired.status == "retired"
    events = audit.list_events(
        AuditEventQuery(tenant_id="default", knowledge_base_id="kb-workflows", limit=10)
    )
    assert [event.action for event in events.items] == [
        "workflow_definition.created",
        "workflow_definition.updated",
        "workflow_definition.approved",
        "workflow_definition.retired",
    ]


def test_update_rejects_approved_definition() -> None:
    _, _, _, service = _service()
    draft = service.create_draft(
        knowledge_base_id="kb-workflows",
        domain_name="medicare_fraud",
        payload=_payload(),
        actor_user_id="analyst-1",
        actor_email=None,
        actor_roles=["analyst"],
        correlation_id="corr-create",
    )
    service.approve_definition(
        knowledge_base_id="kb-workflows",
        definition_id=draft.definition_id,
        version=draft.version,
        actor_user_id="admin-1",
        actor_email=None,
        actor_roles=["admin"],
        correlation_id="corr-approve",
    )

    with pytest.raises(WorkflowDefinitionConflictError, match="Only draft definitions can be updated."):
        service.update_draft(
            knowledge_base_id="kb-workflows",
            definition_id=draft.definition_id,
            version=draft.version,
            payload=_payload(),
            actor_user_id="analyst-1",
            actor_email=None,
            actor_roles=["analyst"],
            correlation_id="corr-update",
        )


def test_run_approved_definition_creates_preview_workflow_run_and_audit_event() -> None:
    _, run_store, audit, service = _service()
    draft = service.create_draft(
        knowledge_base_id="kb-workflows",
        domain_name="medicare_fraud",
        payload=_payload(),
        actor_user_id="analyst-1",
        actor_email=None,
        actor_roles=["analyst"],
        correlation_id="corr-create",
    )
    service.approve_definition(
        knowledge_base_id="kb-workflows",
        definition_id=draft.definition_id,
        version=draft.version,
        actor_user_id="admin-1",
        actor_email=None,
        actor_roles=["admin"],
        correlation_id="corr-approve",
    )

    run = service.run_definition(
        knowledge_base_id="kb-workflows",
        definition_id=draft.definition_id,
        version=draft.version,
        payload=WorkflowDefinitionRunRequest(
            target_type="alert",
            target_id="alert-1",
            inputs={"note": "review current alert"},
            idempotency_key="run-provider-review-alert-1",
        ),
        actor_user_id="analyst-1",
        actor_email="analyst-1@example.com",
        actor_roles=["analyst"],
        correlation_id="corr-run",
    )

    stored = run_store.get_run(run.workflow_id)
    assert stored.workflow_id == run.workflow_id
    assert stored.trigger_event_type == "workflow_definition.requested"
    assert [step.step_name for step in stored.steps] == ["peer-context"]
    assert stored.metadata["definition_id"] == "provider-review-workflow"
    assert stored.metadata["definition_version"] == "v1"
    assert stored.metadata["target_type"] == "alert"
    assert stored.metadata["target_id"] == "alert-1"
    events = audit.list_events(
        AuditEventQuery(
            tenant_id="default",
            knowledge_base_id="kb-workflows",
            action_prefix="workflow_definition.run",
            limit=10,
        )
    )
    assert [event.resource_id for event in events.items] == [
        "provider-review-workflow:v1"
    ]


def test_run_draft_definition_is_rejected() -> None:
    _, _, _, service = _service()
    draft = service.create_draft(
        knowledge_base_id="kb-workflows",
        domain_name="medicare_fraud",
        payload=_payload(),
        actor_user_id="analyst-1",
        actor_email=None,
        actor_roles=["analyst"],
        correlation_id="corr-create",
    )

    with pytest.raises(WorkflowDefinitionConflictError, match="Only approved definitions can be run."):
        service.run_definition(
            knowledge_base_id="kb-workflows",
            definition_id=draft.definition_id,
            version=draft.version,
            payload=WorkflowDefinitionRunRequest(target_type="alert", target_id="alert-1"),
            actor_user_id="analyst-1",
            actor_email=None,
            actor_roles=["analyst"],
            correlation_id="corr-run",
        )


def test_missing_definition_raises_not_found() -> None:
    _, _, _, service = _service()

    with pytest.raises(WorkflowDefinitionNotFoundError, match="not found"):
        service.get_definition(
            knowledge_base_id="kb-workflows",
            definition_id="missing",
            version="v1",
        )
```

- [x] **Step 3: Run RED service and repository tests**

Run:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_in_memory.py backend/tests/workflow_definitions/test_service.py -q
```

Expected: FAIL during import with missing repository and service modules.

- [x] **Step 4: Implement repository protocol and in-memory store**

Create `backend/workflow_definitions/repository.py`:

```python
"""Workflow definition repository boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from workflow_definitions.models import WorkflowDefinition, WorkflowDefinitionPage


@runtime_checkable
class WorkflowDefinitionRepository(Protocol):
    """Store versioned workflow definition snapshots."""

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Store a new workflow definition snapshot."""
        ...

    def update_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Replace an existing workflow definition snapshot."""
        ...

    def get_definition(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition | None:
        """Return one definition by natural key."""
        ...

    def list_definitions(
        self,
        *,
        knowledge_base_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage:
        """Return a deterministic page for one KB."""
        ...


__all__ = ["WorkflowDefinitionRepository"]
```

Create `backend/workflow_definitions/adapters/in_memory.py`:

```python
"""In-memory workflow definition repository."""

from __future__ import annotations

from workflow_definitions.models import WorkflowDefinition, WorkflowDefinitionPage

__all__ = ["InMemoryWorkflowDefinitionRepository"]


class InMemoryWorkflowDefinitionRepository:
    """Dict-backed workflow definition repository for tests and local development."""

    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str, str], WorkflowDefinition] = {}

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        key = _key(definition)
        if key in self._definitions:
            raise ValueError(
                f"Workflow definition '{definition.definition_id}:{definition.version}' already exists."
            )
        stored = definition.model_copy(deep=True)
        self._definitions[key] = stored
        return stored.model_copy(deep=True)

    def update_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        key = _key(definition)
        if key not in self._definitions:
            raise KeyError(
                f"Workflow definition '{definition.definition_id}:{definition.version}' not found."
            )
        stored = definition.model_copy(deep=True)
        self._definitions[key] = stored
        return stored.model_copy(deep=True)

    def get_definition(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition | None:
        definition = self._definitions.get((knowledge_base_id, definition_id, version))
        return definition.model_copy(deep=True) if definition is not None else None

    def list_definitions(
        self,
        *,
        knowledge_base_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage:
        matches = [
            definition.model_copy(deep=True)
            for definition in self._definitions.values()
            if definition.knowledge_base_id == knowledge_base_id
        ]
        matches.sort(key=lambda item: (item.definition_id, item.version))
        if limit <= 0 or offset < 0:
            items: list[WorkflowDefinition] = []
        else:
            items = matches[offset : offset + limit]
        return WorkflowDefinitionPage(
            items=items,
            total=len(matches),
            limit=max(limit, 1),
            offset=max(offset, 0),
        )


def _key(definition: WorkflowDefinition) -> tuple[str, str, str]:
    return (definition.knowledge_base_id, definition.definition_id, definition.version)
```

Create `backend/workflow_definitions/adapters/__init__.py`:

```python
"""Workflow definition repository adapters."""

from __future__ import annotations

from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository

__all__ = ["InMemoryWorkflowDefinitionRepository"]
```

- [x] **Step 5: Implement service lifecycle and preview run handoff**

Create `backend/workflow_definitions/service.py`:

```python
"""Workflow definition lifecycle service."""

from __future__ import annotations

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from auditlog.models import AuditEventCreate
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


class WorkflowDefinitionError(Exception):
    """Base workflow definition service error."""


class WorkflowDefinitionNotFoundError(WorkflowDefinitionError):
    """Raised when a definition is absent."""


class WorkflowDefinitionConflictError(WorkflowDefinitionError):
    """Raised when a lifecycle transition is invalid."""


class WorkflowDefinitionValidationError(WorkflowDefinitionError):
    """Raised when authoring payload validation fails."""


class WorkflowDefinitionService:
    """Coordinates workflow definition validation, storage, audit, and preview runs."""

    def __init__(
        self,
        *,
        repository: WorkflowDefinitionRepository,
        run_store: WorkflowRunStoreProtocol,
        audit_service: AuditLogService | None,
        tenant_id: str = "default",
    ) -> None:
        self._repository = repository
        self._run_store = run_store
        self._audit_service = audit_service
        self._tenant_id = tenant_id

    def list_definitions(
        self,
        *,
        knowledge_base_id: str,
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
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition:
        definition = self._repository.get_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
        )
        if definition is None:
            raise WorkflowDefinitionNotFoundError(
                f"Workflow definition '{definition_id}:{version}' not found."
            )
        return definition

    def create_draft(
        self,
        *,
        knowledge_base_id: str,
        domain_name: str,
        payload: WorkflowDefinitionCreate,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: list[str],
        correlation_id: str,
    ) -> WorkflowDefinition:
        self._raise_if_invalid(payload)
        now = utc_now()
        definition = WorkflowDefinition(
            snapshot_id=f"{knowledge_base_id}:{payload.definition_id}:{payload.version}",
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            definition_id=payload.definition_id,
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
            stored = self._repository.save_definition(definition)
        except ValueError as exc:
            raise WorkflowDefinitionConflictError(str(exc)) from exc
        self._record_event(
            action="workflow_definition.created",
            definition=stored,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
            correlation_id=correlation_id,
        )
        return stored

    def update_draft(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        payload: WorkflowDefinitionCreate | WorkflowDefinitionUpdate,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: list[str],
        correlation_id: str,
    ) -> WorkflowDefinition:
        existing = self.get_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
        )
        if existing.status != "draft":
            raise WorkflowDefinitionConflictError("Only draft definitions can be updated.")
        next_allowed = (
            payload.allowed_capability_refs
            if payload.allowed_capability_refs is not None
            else existing.allowed_capability_refs
        )
        next_steps = payload.steps if payload.steps is not None else existing.steps
        validation_payload = WorkflowDefinitionCreate(
            definition_id=existing.definition_id,
            name=payload.name or existing.name,
            description=payload.description if payload.description is not None else existing.description,
            version=existing.version,
            allowed_capability_refs=list(next_allowed),
            steps=[step.model_copy(deep=True) for step in next_steps],
        )
        self._raise_if_invalid(validation_payload)
        updated = existing.model_copy(
            update={
                "name": validation_payload.name,
                "description": validation_payload.description,
                "allowed_capability_refs": list(validation_payload.allowed_capability_refs),
                "steps": [step.model_copy(deep=True) for step in validation_payload.steps],
                "updated_at": utc_now(),
            },
            deep=True,
        )
        stored = self._repository.update_definition(updated)
        self._record_event(
            action="workflow_definition.updated",
            definition=stored,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
            correlation_id=correlation_id,
        )
        return stored

    def approve_definition(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: list[str],
        correlation_id: str,
    ) -> WorkflowDefinition:
        existing = self.get_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
        )
        if existing.status != "draft":
            raise WorkflowDefinitionConflictError("Only draft definitions can be approved.")
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
        stored = self._repository.update_definition(approved)
        self._record_event(
            action="workflow_definition.approved",
            definition=stored,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
            correlation_id=correlation_id,
        )
        return stored

    def retire_definition(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: list[str],
        correlation_id: str,
    ) -> WorkflowDefinition:
        existing = self.get_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
        )
        if existing.status == "retired":
            return existing
        now = utc_now()
        retired = existing.model_copy(
            update={"status": "retired", "retired_at": now, "updated_at": now},
            deep=True,
        )
        stored = self._repository.update_definition(retired)
        self._record_event(
            action="workflow_definition.retired",
            definition=stored,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
            correlation_id=correlation_id,
        )
        return stored

    def run_definition(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
        payload: WorkflowDefinitionRunRequest,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: list[str],
        correlation_id: str,
    ) -> WorkflowRun:
        definition = self.get_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
        )
        if definition.status != "approved":
            raise WorkflowDefinitionConflictError("Only approved definitions can be run.")
        run = WorkflowRun(
            workflow_id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            trigger_event_type="workflow_definition.requested",
            status=WorkflowRunStatus.QUEUED,
            steps=[WorkflowStepState(step_name=step.step_id) for step in definition.steps],
            metadata={
                "definition_id": definition.definition_id,
                "definition_version": definition.version,
                "definition_status": definition.status,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
                "approved_by": definition.approved_by or "",
            },
            idempotency_key=payload.idempotency_key,
        )
        stored = self._run_store.save_run(run)
        self._record_event(
            action="workflow_definition.run_requested",
            definition=definition,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_roles=actor_roles,
            correlation_id=correlation_id,
            metadata={
                "run_id": stored.workflow_id,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
            },
        )
        return stored

    def _raise_if_invalid(
        self, payload: WorkflowDefinitionCreate | WorkflowDefinitionUpdate
    ) -> None:
        result = validate_workflow_definition_payload(payload)
        if not result.valid:
            raise WorkflowDefinitionValidationError("; ".join(result.errors))

    def _record_event(
        self,
        *,
        action: str,
        definition: WorkflowDefinition,
        actor_user_id: str,
        actor_email: str | None,
        actor_roles: list[str],
        correlation_id: str,
        metadata: dict[str, object | None] | None = None,
    ) -> None:
        if self._audit_service is None:
            return
        event_metadata: dict[str, object | None] = {
            "domain_name": definition.domain_name,
            "definition_id": definition.definition_id,
            "version": definition.version,
        }
        if metadata is not None:
            event_metadata.update(metadata)
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
                correlation_id=correlation_id,
                metadata=event_metadata,
            )
        )


__all__ = [
    "WorkflowDefinitionConflictError",
    "WorkflowDefinitionError",
    "WorkflowDefinitionNotFoundError",
    "WorkflowDefinitionService",
    "WorkflowDefinitionValidationError",
]
```

Update `backend/workflow_definitions/__init__.py` exports to include `WorkflowDefinitionService`, `WorkflowDefinitionRepository`, and `InMemoryWorkflowDefinitionRepository`.

- [x] **Step 6: Run GREEN service tests**

Run:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_in_memory.py backend/tests/workflow_definitions/test_service.py -q
```

Expected: `9 passed`.

- [x] **Step 7: Commit Task 2**

Run:

```bash
git add backend/workflow_definitions backend/tests/workflow_definitions
git commit -m "Add SAFE-CMS-014 workflow definition service"
```

Expected: commit created with models from Task 1 plus the new service and repository files.

## Task 3: API Contracts, Router, and Dependency Wiring

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/app.py`
- Create: `backend/api/routers/workflow_definitions.py`
- Create: `backend/tests/api/test_workflow_definitions_router.py`

- [x] **Step 1: Write RED router tests**

Create `backend/tests/api/test_workflow_definitions_router.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_workflow_definition_service,
)
from api.middleware.auth import get_current_user
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.service import WorkflowDefinitionService


def _domain_with_auth() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _app_for_user(*, roles: list[str], knowledge_base_ids: list[str] | None = None) -> FastAPI:
    app = create_app()
    kb_repository = InMemoryKnowledgeBaseRepository()
    kb_repository.create(
        KnowledgeBase(
            id="kb-workflows",
            name="Workflow KB",
            description="Workflow API test KB",
            domain="medicare_fraud",
            domain_name="medicare_fraud",
        )
    )
    definition_repository = InMemoryWorkflowDefinitionRepository()
    run_store = InMemoryWorkflowRunStore()
    audit = AuditLogService(InMemoryAuditLogRepository())
    service = WorkflowDefinitionService(
        repository=definition_repository,
        run_store=run_store,
        audit_service=audit,
    )
    app.dependency_overrides[get_domain_config] = _domain_with_auth
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_workflow_definition_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id=f"{roles[0] if roles else 'user'}-1",
        roles=roles,
        email=f"{roles[0] if roles else 'user'}-1@example.com",
        knowledge_base_ids=knowledge_base_ids,
    )
    app.state.workflow_definition_test_audit = audit
    return app


def _payload() -> dict[str, object]:
    return {
        "definition_id": "provider-review-workflow",
        "name": "Provider review workflow",
        "description": "Review provider outlier alerts.",
        "version": "v1",
        "allowed_capability_refs": ["analytics.peer_context"],
        "steps": [
            {
                "step_id": "peer-context",
                "label": "Peer context",
                "capability_ref": "analytics.peer_context",
                "input_refs": ["alert.provider_npi"],
                "output_refs": ["peer_context"],
            }
        ],
    }


def test_analyst_can_create_draft_and_viewer_can_read_it() -> None:
    app = _app_for_user(roles=["analyst"], knowledge_base_ids=["kb-workflows"])
    client = TestClient(app)

    create_response = client.post(
        "/knowledgebases/kb-workflows/workflow-definitions",
        json=_payload(),
    )
    list_response = client.get("/knowledgebases/kb-workflows/workflow-definitions")

    assert create_response.status_code == 200
    assert create_response.json()["status"] == "draft"
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["definition_id"] == "provider-review-workflow"


def test_viewer_cannot_create_definition() -> None:
    app = _app_for_user(roles=["viewer"], knowledge_base_ids=["kb-workflows"])

    response = TestClient(app).post(
        "/knowledgebases/kb-workflows/workflow-definitions",
        json=_payload(),
    )

    assert response.status_code == 403


def test_admin_can_approve_and_analyst_can_run_approved_definition() -> None:
    app = _app_for_user(roles=["admin"], knowledge_base_ids=["kb-workflows"])
    client = TestClient(app)
    created = client.post(
        "/knowledgebases/kb-workflows/workflow-definitions",
        json=_payload(),
    )
    assert created.status_code == 200
    approved = client.post(
        "/knowledgebases/kb-workflows/workflow-definitions/provider-review-workflow/versions/v1/approve"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="analyst-1",
        roles=["analyst"],
        email="analyst-1@example.com",
        knowledge_base_ids=["kb-workflows"],
    )

    run = client.post(
        "/knowledgebases/kb-workflows/workflow-definitions/provider-review-workflow/versions/v1/run",
        json={
            "target_type": "alert",
            "target_id": "alert-1",
            "inputs": {"note": "review current alert"},
            "idempotency_key": "workflow-run-alert-1",
        },
    )

    assert run.status_code == 200
    assert run.json()["status"] == "queued"
    assert run.json()["current_step"] == "peer-context"


def test_analyst_cannot_approve_definition() -> None:
    app = _app_for_user(roles=["analyst"], knowledge_base_ids=["kb-workflows"])
    client = TestClient(app)
    assert client.post(
        "/knowledgebases/kb-workflows/workflow-definitions",
        json=_payload(),
    ).status_code == 200

    response = client.post(
        "/knowledgebases/kb-workflows/workflow-definitions/provider-review-workflow/versions/v1/approve"
    )

    assert response.status_code == 403


def test_run_draft_returns_conflict() -> None:
    app = _app_for_user(roles=["analyst"], knowledge_base_ids=["kb-workflows"])
    client = TestClient(app)
    assert client.post(
        "/knowledgebases/kb-workflows/workflow-definitions",
        json=_payload(),
    ).status_code == 200

    response = client.post(
        "/knowledgebases/kb-workflows/workflow-definitions/provider-review-workflow/versions/v1/run",
        json={"target_type": "alert", "target_id": "alert-1"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only approved definitions can be run."


def test_out_of_scope_knowledge_base_returns_404() -> None:
    app = _app_for_user(roles=["analyst"], knowledge_base_ids=["kb-other"])

    response = TestClient(app).get(
        "/knowledgebases/kb-workflows/workflow-definitions"
    )

    assert response.status_code == 404
```

- [x] **Step 2: Run RED router tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_workflow_definitions_router.py -q
```

Expected: FAIL during import because `get_workflow_definition_service` is not defined or route returns 404 because the router is not registered.

- [x] **Step 3: Add API contracts**

Append to `backend/api/contracts.py` near the workflow/playbook response models:

```python
class WorkflowStepDefinitionPayload(BaseModel):
    """Workflow step authoring payload."""

    step_id: str
    label: str
    capability_ref: str
    input_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    output_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    condition: str | None = None
    retry_policy: dict[str, int] | None = None
    requires_human_approval: bool = False
    on_failure: Literal["fail_workflow", "continue", "require_approval"] = "fail_workflow"


class WorkflowDefinitionCreatePayload(BaseModel):
    """Workflow definition draft creation payload."""

    definition_id: str
    name: str
    description: str = ""
    version: str
    allowed_capability_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    steps: list[WorkflowStepDefinitionPayload]


class WorkflowDefinitionUpdatePayload(BaseModel):
    """Workflow definition draft update payload."""

    name: str | None = None
    description: str | None = None
    allowed_capability_refs: list[str] | None = None
    steps: list[WorkflowStepDefinitionPayload] | None = None


class WorkflowDefinitionRunRequestPayload(BaseModel):
    """Request to create a preview run for an approved definition."""

    target_type: Literal["alert", "entity", "case", "knowledge_base"]
    target_id: str
    inputs: dict[str, str | int | float | bool] = Field(
        default_factory=lambda: cast(dict[str, str | int | float | bool], {})
    )
    idempotency_key: str | None = None


class WorkflowStepDefinitionResponse(BaseModel):
    """Workflow step response."""

    step_id: str
    label: str
    capability_ref: str
    input_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    output_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    condition: str | None = None
    retry_policy: dict[str, int] | None = None
    requires_human_approval: bool = False
    on_failure: Literal["fail_workflow", "continue", "require_approval"] = "fail_workflow"


class WorkflowDefinitionResponse(BaseModel):
    """Workflow definition response."""

    snapshot_id: str
    knowledge_base_id: str
    domain_name: str
    definition_id: str
    name: str
    description: str
    version: str
    status: Literal["draft", "approved", "retired"]
    allowed_capability_refs: list[str] = Field(default_factory=lambda: cast(list[str], []))
    steps: list[WorkflowStepDefinitionResponse] = Field(
        default_factory=lambda: cast(list[WorkflowStepDefinitionResponse], [])
    )
    created_by: str
    approved_by: str | None = None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    retired_at: datetime | None = None


class WorkflowDefinitionListResponse(BaseModel):
    """Workflow definition list response."""

    items: list[WorkflowDefinitionResponse] = Field(
        default_factory=lambda: cast(list[WorkflowDefinitionResponse], [])
    )
    total: int
    limit: int
    offset: int
```

Add all new contract class names to the `__all__` list in `backend/api/contracts.py`.

- [x] **Step 4: Add router**

Create `backend/api/routers/workflow_definitions.py`:

```python
"""KB-scoped workflow definition API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from api._workflow_projection import project_workflow_run
from api.contracts import (
    WorkflowDefinitionCreatePayload,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowDefinitionRunRequestPayload,
    WorkflowDefinitionUpdatePayload,
    WorkflowRunResponse,
    WorkflowStepDefinitionPayload,
    WorkflowStepDefinitionResponse,
)
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_workflow_definition_service,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from config.schema import DomainConfig
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import KnowledgeBase
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRunRequest,
    WorkflowDefinitionUpdate,
    WorkflowRetryPolicy,
    WorkflowStepDefinition,
)
from workflow_definitions.service import (
    WorkflowDefinitionConflictError,
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionService,
    WorkflowDefinitionValidationError,
)

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/workflow-definitions",
    tags=["workflow-definitions"],
)


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = user.knowledge_base_ids
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _require_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository,
    user: User,
    domain_config: DomainConfig,
) -> tuple[KnowledgeBase, str]:
    if not _can_access_knowledge_base(user, knowledge_base_id):
        raise _not_found("Knowledge base", knowledge_base_id)
    kb = repository.get(knowledge_base_id)
    if kb is None:
        raise _not_found("Knowledge base", knowledge_base_id)
    domain_name = getattr(kb, "domain_name", None)
    if isinstance(domain_name, str) and domain_name:
        return kb, domain_name
    return kb, kb.domain or domain_config.domain.name


@router.get("", response_model=WorkflowDefinitionListResponse)
def list_workflow_definitions(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> WorkflowDefinitionListResponse:
    """Return workflow definitions for one KB."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    page = service.list_definitions(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        offset=offset,
    )
    return WorkflowDefinitionListResponse(
        items=[_definition_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=WorkflowDefinitionResponse)
def create_workflow_definition(
    knowledge_base_id: str,
    payload: WorkflowDefinitionCreatePayload,
    request: Request,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> WorkflowDefinitionResponse:
    """Create a draft workflow definition."""
    _, domain_name = _require_knowledge_base(
        knowledge_base_id, kb_repository, user, domain_config
    )
    try:
        definition = service.create_draft(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            payload=_create_payload(payload),
            actor_user_id=user.user_id,
            actor_email=user.email,
            actor_roles=list(user.roles),
            correlation_id=_correlation_id(request),
        )
    except WorkflowDefinitionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except WorkflowDefinitionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _definition_response(definition)


@router.get("/{definition_id}/versions/{version}", response_model=WorkflowDefinitionResponse)
def get_workflow_definition(
    knowledge_base_id: str,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> WorkflowDefinitionResponse:
    """Return one workflow definition version."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        definition = service.get_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    return _definition_response(definition)


@router.put("/{definition_id}/versions/{version}", response_model=WorkflowDefinitionResponse)
def update_workflow_definition(
    knowledge_base_id: str,
    payload: WorkflowDefinitionUpdatePayload,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> WorkflowDefinitionResponse:
    """Update a draft workflow definition."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        definition = service.update_draft(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
            payload=_update_payload(payload),
            actor_user_id=user.user_id,
            actor_email=user.email,
            actor_roles=list(user.roles),
            correlation_id=_correlation_id(request),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except WorkflowDefinitionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _definition_response(definition)


@router.post("/{definition_id}/versions/{version}/approve", response_model=WorkflowDefinitionResponse)
def approve_workflow_definition(
    knowledge_base_id: str,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> WorkflowDefinitionResponse:
    """Approve a draft workflow definition."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        definition = service.approve_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
            actor_user_id=user.user_id,
            actor_email=user.email,
            actor_roles=list(user.roles),
            correlation_id=_correlation_id(request),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _definition_response(definition)


@router.post("/{definition_id}/versions/{version}/retire", response_model=WorkflowDefinitionResponse)
def retire_workflow_definition(
    knowledge_base_id: str,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> WorkflowDefinitionResponse:
    """Retire a workflow definition."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        definition = service.retire_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
            actor_user_id=user.user_id,
            actor_email=user.email,
            actor_roles=list(user.roles),
            correlation_id=_correlation_id(request),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    return _definition_response(definition)


@router.post("/{definition_id}/versions/{version}/run", response_model=WorkflowRunResponse)
def run_workflow_definition(
    knowledge_base_id: str,
    payload: WorkflowDefinitionRunRequestPayload,
    request: Request,
    definition_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("analyst")),
) -> WorkflowRunResponse:
    """Create a preview workflow run from an approved definition."""
    _require_knowledge_base(knowledge_base_id, kb_repository, user, domain_config)
    try:
        run = service.run_definition(
            knowledge_base_id=knowledge_base_id,
            definition_id=definition_id,
            version=version,
            payload=WorkflowDefinitionRunRequest.model_validate(payload.model_dump()),
            actor_user_id=user.user_id,
            actor_email=user.email,
            actor_roles=list(user.roles),
            correlation_id=_correlation_id(request),
        )
    except WorkflowDefinitionNotFoundError as exc:
        raise _not_found("Workflow definition", f"{definition_id}:{version}") from exc
    except WorkflowDefinitionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return project_workflow_run(run)


def _create_payload(payload: WorkflowDefinitionCreatePayload) -> WorkflowDefinitionCreate:
    return WorkflowDefinitionCreate(
        definition_id=payload.definition_id,
        name=payload.name,
        description=payload.description,
        version=payload.version,
        allowed_capability_refs=list(payload.allowed_capability_refs),
        steps=[_step_payload(step) for step in payload.steps],
    )


def _update_payload(payload: WorkflowDefinitionUpdatePayload) -> WorkflowDefinitionUpdate:
    return WorkflowDefinitionUpdate(
        name=payload.name,
        description=payload.description,
        allowed_capability_refs=(
            None if payload.allowed_capability_refs is None else list(payload.allowed_capability_refs)
        ),
        steps=None if payload.steps is None else [_step_payload(step) for step in payload.steps],
    )


def _step_payload(payload: WorkflowStepDefinitionPayload) -> WorkflowStepDefinition:
    return WorkflowStepDefinition(
        step_id=payload.step_id,
        label=payload.label,
        capability_ref=payload.capability_ref,
        input_refs=list(payload.input_refs),
        output_refs=list(payload.output_refs),
        condition=payload.condition,
        retry_policy=(
            None if payload.retry_policy is None else WorkflowRetryPolicy.model_validate(payload.retry_policy)
        ),
        requires_human_approval=payload.requires_human_approval,
        on_failure=payload.on_failure,
    )


def _definition_response(definition: WorkflowDefinition) -> WorkflowDefinitionResponse:
    return WorkflowDefinitionResponse(
        snapshot_id=definition.snapshot_id,
        knowledge_base_id=definition.knowledge_base_id,
        domain_name=definition.domain_name,
        definition_id=definition.definition_id,
        name=definition.name,
        description=definition.description,
        version=definition.version,
        status=definition.status,
        allowed_capability_refs=list(definition.allowed_capability_refs),
        steps=[
            WorkflowStepDefinitionResponse(
                step_id=step.step_id,
                label=step.label,
                capability_ref=step.capability_ref,
                input_refs=list(step.input_refs),
                output_refs=list(step.output_refs),
                condition=step.condition,
                retry_policy=None if step.retry_policy is None else step.retry_policy.model_dump(mode="json"),
                requires_human_approval=step.requires_human_approval,
                on_failure=step.on_failure,
            )
            for step in definition.steps
        ],
        created_by=definition.created_by,
        approved_by=definition.approved_by,
        created_at=definition.created_at,
        updated_at=definition.updated_at,
        approved_at=definition.approved_at,
        retired_at=definition.retired_at,
    )


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or "workflow-definition-request"


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )
```

- [x] **Step 5: Wire dependencies and app registration**

In `backend/api/dependencies.py`, add imports:

```python
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.repository import WorkflowDefinitionRepository
from workflow_definitions.service import WorkflowDefinitionService
```

Add factories near `get_playbook_repository`:

```python
def get_workflow_definition_repository(request: Request) -> WorkflowDefinitionRepository:
    """Return the workflow definition repository.

    Task 4 replaces this in-memory factory with the Postgres-aware factory
    after the durable adapter exists.
    """

    return _memoize_config_derived(
        request.app,
        "workflow_definition_repository",
        lambda: InMemoryWorkflowDefinitionRepository(),
        guard=lambda value: isinstance(value, WorkflowDefinitionRepository),
    )


def get_workflow_definition_service(
    repository: WorkflowDefinitionRepository = Depends(get_workflow_definition_repository),
    run_store: WorkflowRunStoreProtocol = Depends(get_workflow_run_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
) -> WorkflowDefinitionService:
    """Return the workflow definition service."""

    return WorkflowDefinitionService(
        repository=repository,
        run_store=run_store,
        audit_service=audit_service,
    )
```

Add `"workflow_definition_repository"` to `_CONFIG_DERIVED_APP_STATE_ATTRS`.

Add both new factories to `__all__` if the module maintains the exported names near the top of the file.

In `backend/api/app.py`, add the import:

```python
from api.routers.workflow_definitions import router as workflow_definitions_router
```

Register it near playbooks/workflows:

```python
app.include_router(workflow_definitions_router)
```

- [x] **Step 6: Run router tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_workflow_definitions_router.py -q
```

Expected: `6 passed`.

- [x] **Step 7: Commit Task 3**

Run:

```bash
git add backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/workflow_definitions.py backend/tests/api/test_workflow_definitions_router.py
git commit -m "Expose SAFE-CMS-014 workflow definition API"
```

Expected: commit created with API-only changes.

## Task 4: Postgres Repository and Migration

**Files:**
- Create: `backend/database/migrations/versions/0021_workflow_definition_snapshots.py`
- Create: `backend/workflow_definitions/adapters/postgres.py`
- Modify: `backend/workflow_definitions/adapters/__init__.py`
- Modify: `backend/api/dependencies.py`
- Create: `backend/tests/workflow_definitions/test_postgres.py`
- Create: `backend/tests/database/test_workflow_definitions_migration.py`
- Modify: `backend/database/migrations/snapshots/head.sql`

- [x] **Step 1: Write RED migration declaration test**

Create `backend/tests/database/test_workflow_definitions_migration.py`:

```python
from __future__ import annotations

from pathlib import Path


def test_workflow_definition_migration_declares_snapshot_table() -> None:
    migration = (
        Path("backend")
        / "database/migrations/versions/0021_workflow_definition_snapshots.py"
    ).read_text(encoding="utf-8")

    assert "down_revision: str | None = \"0020_playbook_snapshot_kb_scope\"" in migration
    assert "CREATE TABLE IF NOT EXISTS workflow_definition_snapshots" in migration
    assert "PRIMARY KEY (knowledge_base_id, definition_id, version)" in migration
    assert "allowed_capability_refs jsonb NOT NULL" in migration
    assert "steps jsonb NOT NULL" in migration
    assert "ix_workflow_definition_snapshots_kb_status" in migration
```

- [x] **Step 2: Write RED Postgres repository tests**

Create `backend/tests/workflow_definitions/test_postgres.py`:

```python
"""Integration tests for SAFE-CMS-014 Postgres workflow definitions."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from workflow_definitions.adapters.postgres import PostgresWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinition, WorkflowStepDefinition

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_KB_ID = "kb-safe-cms-014-pg"

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping workflow definition integration tests.")
    return url


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert connection_provider is not None
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM workflow_definition_snapshots WHERE knowledge_base_id = %s",
            (_KB_ID,),
        )
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM workflow_definition_snapshots WHERE knowledge_base_id = %s",
            (_KB_ID,),
        )
        conn.commit()
    connection_provider.close()


def _definition(
    *,
    definition_id: str = "provider-review-workflow",
    version: str = "v1",
    name: str = "Provider review workflow",
) -> WorkflowDefinition:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    return WorkflowDefinition(
        snapshot_id=f"{_KB_ID}:{definition_id}:{version}",
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
        definition_id=definition_id,
        name=name,
        description="Review provider outlier alerts.",
        version=version,
        status="draft",
        allowed_capability_refs=["analytics.peer_context"],
        steps=[
            WorkflowStepDefinition(
                step_id="peer-context",
                label="Peer context",
                capability_ref="analytics.peer_context",
            )
        ],
        created_by="analyst-1",
        created_at=now,
        updated_at=now,
    )


def test_postgres_repository_round_trips_definition(provider: ConnectionProvider) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)

    stored = repository.save_definition(_definition())
    found = repository.get_definition(
        knowledge_base_id=_KB_ID,
        definition_id="provider-review-workflow",
        version="v1",
    )

    assert found is not None
    assert stored == found
    assert found.steps[0].capability_ref == "analytics.peer_context"


def test_postgres_repository_updates_existing_definition(provider: ConnectionProvider) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)
    repository.save_definition(_definition())
    updated = _definition(name="Updated provider review workflow")

    stored = repository.update_definition(updated)

    assert stored.name == "Updated provider review workflow"


def test_postgres_repository_lists_by_knowledge_base(provider: ConnectionProvider) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)
    repository.save_definition(_definition(definition_id="z-workflow", version="v2"))
    repository.save_definition(_definition(definition_id="a-workflow", version="v1"))

    page = repository.list_definitions(knowledge_base_id=_KB_ID, limit=1, offset=1)

    assert page.total == 2
    assert [(item.definition_id, item.version) for item in page.items] == [
        ("z-workflow", "v2")
    ]
```

- [x] **Step 3: Run RED migration and Postgres tests**

Run:

```bash
uv run --project backend pytest backend/tests/database/test_workflow_definitions_migration.py -q
```

Expected: FAIL with `FileNotFoundError` for `0021_workflow_definition_snapshots.py`.

Run only if `DATABASE_URL` points to the dev Postgres:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_postgres.py -q
```

Expected: FAIL during import because `PostgresWorkflowDefinitionRepository` does not exist, or SKIP if `DATABASE_URL` is unset.

- [x] **Step 4: Add migration**

Create `backend/database/migrations/versions/0021_workflow_definition_snapshots.py`:

```python
"""Add workflow definition snapshots.

Revision ID: 0021_workflow_definition_snapshots
Revises: 0020_playbook_snapshot_kb_scope
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op

revision: str = "0021_workflow_definition_snapshots"
down_revision: str | None = "0020_playbook_snapshot_kb_scope"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_definition_snapshots (
            snapshot_id text NOT NULL,
            knowledge_base_id text NOT NULL,
            domain_name text NOT NULL,
            definition_id text NOT NULL,
            version text NOT NULL,
            status text NOT NULL,
            name text NOT NULL,
            description text NOT NULL DEFAULT '',
            allowed_capability_refs jsonb NOT NULL,
            steps jsonb NOT NULL,
            created_by text NOT NULL,
            approved_by text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            approved_at timestamptz,
            retired_at timestamptz,
            CONSTRAINT pk_workflow_definition_snapshots
                PRIMARY KEY (knowledge_base_id, definition_id, version),
            CONSTRAINT ck_workflow_definition_snapshots_status
                CHECK (status IN ('draft', 'approved', 'retired'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_definition_snapshots_kb_status
        ON workflow_definition_snapshots (
            knowledge_base_id, status, updated_at DESC
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_workflow_definition_snapshots_kb_status")
    op.execute("DROP TABLE IF EXISTS workflow_definition_snapshots")
```

- [x] **Step 5: Add Postgres repository**

Create `backend/workflow_definitions/adapters/postgres.py`:

```python
"""Postgres-backed workflow definition repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from database.protocols import ConnectionProvider, Row
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionPage,
    WorkflowDefinitionStatus,
    WorkflowStepDefinition,
)

__all__ = ["PostgresWorkflowDefinitionRepository"]

_COLUMNS = (
    "snapshot_id, knowledge_base_id, domain_name, definition_id, version, status, "
    "name, description, allowed_capability_refs, steps, created_by, approved_by, "
    "created_at, updated_at, approved_at, retired_at"
)


class PostgresWorkflowDefinitionRepository:
    """Store workflow definition snapshots in Postgres."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        with self._provider.connection() as conn:
            conn.execute(
                f"""
                INSERT INTO workflow_definition_snapshots ({_COLUMNS})
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                _params(definition),
            )
            conn.commit()
        stored = self.get_definition(
            knowledge_base_id=definition.knowledge_base_id,
            definition_id=definition.definition_id,
            version=definition.version,
        )
        if stored is None:
            raise ValueError(
                f"Workflow definition '{definition.definition_id}:{definition.version}' was not stored."
            )
        return stored

    def update_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        with self._provider.connection() as conn:
            conn.execute(
                """
                UPDATE workflow_definition_snapshots
                SET snapshot_id = %s,
                    domain_name = %s,
                    status = %s,
                    name = %s,
                    description = %s,
                    allowed_capability_refs = %s::jsonb,
                    steps = %s::jsonb,
                    created_by = %s,
                    approved_by = %s,
                    created_at = %s,
                    updated_at = %s,
                    approved_at = %s,
                    retired_at = %s
                WHERE knowledge_base_id = %s
                  AND definition_id = %s
                  AND version = %s
                """,
                (
                    definition.snapshot_id,
                    definition.domain_name,
                    definition.status,
                    definition.name,
                    definition.description,
                    json.dumps(definition.allowed_capability_refs),
                    json.dumps([step.model_dump(mode="json") for step in definition.steps]),
                    definition.created_by,
                    definition.approved_by,
                    definition.created_at,
                    definition.updated_at,
                    definition.approved_at,
                    definition.retired_at,
                    definition.knowledge_base_id,
                    definition.definition_id,
                    definition.version,
                ),
            )
            conn.commit()
        stored = self.get_definition(
            knowledge_base_id=definition.knowledge_base_id,
            definition_id=definition.definition_id,
            version=definition.version,
        )
        if stored is None:
            raise KeyError(
                f"Workflow definition '{definition.definition_id}:{definition.version}' not found."
            )
        return stored

    def get_definition(
        self,
        *,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                f"""
                SELECT {_COLUMNS}
                FROM workflow_definition_snapshots
                WHERE knowledge_base_id = %s AND definition_id = %s AND version = %s
                """,
                (knowledge_base_id, definition_id, version),
            ).fetchone()
        return None if row is None else _row_to_definition(row)

    def list_definitions(
        self,
        *,
        knowledge_base_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage:
        with self._provider.connection() as conn:
            total_row = conn.execute(
                """
                SELECT count(*)
                FROM workflow_definition_snapshots
                WHERE knowledge_base_id = %s
                """,
                (knowledge_base_id,),
            ).fetchone()
            total = cast(int, total_row[0]) if total_row is not None else 0
            rows = (
                []
                if limit <= 0 or offset < 0
                else conn.execute(
                    f"""
                    SELECT {_COLUMNS}
                    FROM workflow_definition_snapshots
                    WHERE knowledge_base_id = %s
                    ORDER BY definition_id ASC, version ASC
                    LIMIT %s OFFSET %s
                    """,
                    (knowledge_base_id, limit, offset),
                ).fetchall()
            )
        return WorkflowDefinitionPage(
            items=[_row_to_definition(row) for row in rows],
            total=total,
            limit=max(limit, 1),
            offset=max(offset, 0),
        )


def _params(definition: WorkflowDefinition) -> tuple[object, ...]:
    return (
        definition.snapshot_id,
        definition.knowledge_base_id,
        definition.domain_name,
        definition.definition_id,
        definition.version,
        definition.status,
        definition.name,
        definition.description,
        json.dumps(definition.allowed_capability_refs),
        json.dumps([step.model_dump(mode="json") for step in definition.steps]),
        definition.created_by,
        definition.approved_by,
        definition.created_at,
        definition.updated_at,
        definition.approved_at,
        definition.retired_at,
    )


def _row_to_definition(row: Row) -> WorkflowDefinition:
    raw_steps = json.loads(row[9]) if isinstance(row[9], (str, bytes, bytearray)) else row[9]
    raw_capabilities = json.loads(row[8]) if isinstance(row[8], (str, bytes, bytearray)) else row[8]
    return WorkflowDefinition(
        snapshot_id=cast(str, row[0]),
        knowledge_base_id=cast(str, row[1]),
        domain_name=cast(str, row[2]),
        definition_id=cast(str, row[3]),
        version=cast(str, row[4]),
        status=cast(WorkflowDefinitionStatus, row[5]),
        name=cast(str, row[6]),
        description=cast(str, row[7]),
        allowed_capability_refs=list(cast(list[str], raw_capabilities)),
        steps=[WorkflowStepDefinition.model_validate(step) for step in cast(list[object], raw_steps)],
        created_by=cast(str, row[10]),
        approved_by=cast(str | None, row[11]),
        created_at=cast(datetime, row[12]),
        updated_at=cast(datetime, row[13]),
        approved_at=cast(datetime | None, row[14]),
        retired_at=cast(datetime | None, row[15]),
    )
```

Update `backend/workflow_definitions/adapters/__init__.py`:

```python
"""Workflow definition repository adapters."""

from __future__ import annotations

from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.adapters.postgres import PostgresWorkflowDefinitionRepository

__all__ = [
    "InMemoryWorkflowDefinitionRepository",
    "PostgresWorkflowDefinitionRepository",
]
```

- [x] **Step 6: Switch dependency factory to Postgres when configured**

In `backend/api/dependencies.py`, add this import:

```python
from workflow_definitions.adapters.postgres import PostgresWorkflowDefinitionRepository
```

Replace `get_workflow_definition_repository` with:

```python
def get_workflow_definition_repository(request: Request) -> WorkflowDefinitionRepository:
    """Return the workflow definition repository selected by database backend."""

    def build() -> WorkflowDefinitionRepository:
        provider = get_connection_provider()
        if provider is None:
            return InMemoryWorkflowDefinitionRepository()
        return PostgresWorkflowDefinitionRepository(provider)

    return _memoize_config_derived(
        request.app,
        "workflow_definition_repository",
        build,
        guard=lambda value: isinstance(value, WorkflowDefinitionRepository),
    )
```

- [x] **Step 7: Run migration and repository tests**

Run:

```bash
uv run --project backend pytest backend/tests/database/test_workflow_definitions_migration.py -q
```

Expected: `1 passed`.

Run with `DATABASE_URL` set:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_postgres.py -q
```

Expected: `3 passed`, or SKIP if `DATABASE_URL` is unset.

- [x] **Step 8: Regenerate migration snapshot**

Run:

```bash
scripts/ci_migration_check.sh --update-snapshot
```

Expected: command exits 0 and prints `OK: snapshot written:` with `backend/database/migrations/snapshots/head.sql`.

- [x] **Step 9: Verify migration replay has no drift**

Run:

```bash
scripts/ci_migration_check.sh
rg -n "CREATE TABLE public.workflow_definition_snapshots" backend/database/migrations/snapshots/head.sql
```

Expected: migration check exits 0 and prints `OK: migration replay clean`; `rg` finds the new snapshot table.

- [x] **Step 10: Commit Task 4**

Run:

```bash
git add backend/database/migrations/versions/0021_workflow_definition_snapshots.py backend/database/migrations/snapshots/head.sql backend/workflow_definitions/adapters/postgres.py backend/workflow_definitions/adapters/__init__.py backend/api/dependencies.py backend/tests/workflow_definitions/test_postgres.py backend/tests/database/test_workflow_definitions_migration.py
git commit -m "Persist SAFE-CMS-014 workflow definitions"
```

Expected: commit created with migration, snapshot, Postgres adapter, and tests.

## Task 5: Contract Regeneration and Final Verification

**Files:**
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Modify if needed: `chili_app/src/api/contracts.ts`

- [x] **Step 1: Export OpenAPI**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
```

Expected: command exits 0 and `chili_app/openapi.json` includes `/knowledgebases/{knowledge_base_id}/workflow-definitions`.

- [x] **Step 2: Run frontend API codegen**

Run:

```bash
cd chili_app && npm run codegen:api
```

Expected: command exits 0 and `chili_app/src/lib/api/schema.ts` includes `WorkflowDefinitionResponse`.

- [x] **Step 3: Run focused backend tests**

Run:

```bash
uv run --project backend pytest \
  backend/tests/workflow_definitions/test_models.py \
  backend/tests/workflow_definitions/test_in_memory.py \
  backend/tests/workflow_definitions/test_service.py \
  backend/tests/api/test_workflow_definitions_router.py \
  backend/tests/database/test_workflow_definitions_migration.py \
  backend/tests/api/test_workflows_router.py \
  backend/tests/api/test_playbooks_router.py \
  -q
```

Expected: all selected tests pass.

- [x] **Step 4: Run integration test when Postgres is available**

Run with `DATABASE_URL` set:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_postgres.py -q
```

Expected: `3 passed`, or SKIP if `DATABASE_URL` is unset.

- [x] **Step 5: Run static checks**

Run:

```bash
uv run --project backend ruff check backend
uv run --project backend pyright
```

Expected: Ruff exits 0. Pyright reports `0 errors`.

- [x] **Step 6: Run generated contract drift check**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` exits 0. `git status --short` shows only intended SAFE-CMS-014 files and generated contract files.

- [x] **Step 7: Commit Task 5**

Run:

```bash
git add chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts
git commit -m "Regenerate SAFE-CMS-014 workflow definition contracts"
```

Expected: commit created if generated files changed. If only backend generated files changed and `chili_app/src/api/contracts.ts` did not change, omit `chili_app/src/api/contracts.ts` from `git add`.

## Task 6: Review, Fix, and Close the Slice

**Files:**
- Modify only files identified by focused review findings.

- [x] **Step 1: Request focused code review**

Use `superpowers:requesting-code-review` with this prompt:

```text
Review SAFE-CMS-014 workflow definition implementation for blockers only.

Focus on:
- KB scoping and 404 behavior for unauthorized KBs.
- RBAC split: viewer read, analyst draft/run, admin approve/retire.
- Validation before persistence for unknown or unauthorized capability refs.
- Audit events for create, update, approve, retire, and run request.
- Preview run metadata and interaction with existing WorkflowRunStoreProtocol.
- Postgres migration durability and snapshot drift.

Do not suggest broad UI work or Flowise integration; those are out of scope for this slice.
```

Expected: review returns either no blockers or concrete file/line findings.

- [x] **Step 2: Fix review findings with TDD**

For each blocker, write a focused failing test in the nearest existing test file, run it to confirm RED, patch the production file, then rerun that test to confirm GREEN.

Example command shape:

```bash
uv run --project backend pytest backend/tests/api/test_workflow_definitions_router.py::test_out_of_scope_knowledge_base_returns_404 -q
```

Expected: the new or updated test fails before the fix and passes after the fix.

- [x] **Step 3: Run final verification**

Run:

```bash
uv run --project backend pytest \
  backend/tests/workflow_definitions/test_models.py \
  backend/tests/workflow_definitions/test_in_memory.py \
  backend/tests/workflow_definitions/test_service.py \
  backend/tests/api/test_workflow_definitions_router.py \
  backend/tests/database/test_workflow_definitions_migration.py \
  backend/tests/api/test_workflows_router.py \
  backend/tests/api/test_playbooks_router.py \
  -q
uv run --project backend ruff check backend
uv run --project backend pyright
git diff --check
```

Expected: tests pass, Ruff exits 0, Pyright reports `0 errors`, and `git diff --check` exits 0.

- [x] **Step 4: Commit review fixes**

Run:

```bash
git add backend chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts
git commit -m "Address SAFE-CMS-014 workflow definition review"
```

Expected: commit created only if review fixes changed files. If there are no review findings, skip this commit and record that no changes were needed.

- [x] **Step 5: Final branch status**

Run:

```bash
git status --short --branch
git log --oneline -6
```

Expected: worktree clean, branch remains `safe-cms-013-playbooks`, and recent commits show the SAFE-CMS-014 implementation commits.

## Acceptance Check

Before declaring completion, verify these statements from the spec:

- Workflow definitions are durable, versioned, KB-scoped, and RBAC protected.
- Invalid capability refs fail before persistence.
- Analysts can create drafts and run approved definitions only.
- Admins can approve and retire definitions.
- Preview runs appear through existing `/workflows` list/detail behavior.
- Audit events exist for create, update, approve, retire, and run request.
- OpenAPI and generated frontend schema match backend contracts.
