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
