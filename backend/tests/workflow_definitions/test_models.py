from __future__ import annotations

import pytest
from pydantic import ValidationError

import workflow_definitions
from workflow_definitions.models import (
    BUILT_IN_WORKFLOW_CAPABILITIES,
    MetadataValue,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowFailureMode,
    WorkflowDefinitionRunRequest,
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


def test_definition_create_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        WorkflowDefinitionCreate(
            definition_id="provider-review-workflow",
            name="Provider review workflow",
            version="v1",
            allowed_capability_refs=["rag.query"],
            steps=[],
        )


def test_definition_update_requires_at_least_one_step_when_steps_are_provided() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        WorkflowDefinitionUpdate(steps=[])


def test_definition_snapshot_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        WorkflowDefinition(
            definition_id="provider-review-workflow",
            knowledge_base_id="kb-1",
            name="Provider review workflow",
            version="v1",
            allowed_capability_refs=["rag.query"],
            steps=[],
            created_by="analyst-1",
        )


def test_retry_policy_requires_positive_attempts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        WorkflowStepDefinition.model_validate(
            {
                "step_id": "peer-context",
                "label": "Peer context",
                "capability_ref": "analytics.peer_context",
                "retry_policy": {"max_attempts": 0},
            }
        )


def test_run_request_inputs_accept_only_scalar_metadata_values() -> None:
    assert MetadataValue == getattr(workflow_definitions, "MetadataValue")
    request = WorkflowDefinitionRunRequest(
        target_type="alert",
        target_id="alert-123",
        inputs={"query": "peer review", "count": 3, "score": 0.75, "urgent": True},
    )

    assert request.inputs == {
        "query": "peer review",
        "count": 3,
        "score": 0.75,
        "urgent": True,
    }
    with pytest.raises(ValidationError):
        WorkflowDefinitionRunRequest.model_validate(
            {
                "target_type": "alert",
                "target_id": "alert-123",
                "inputs": {"nested": {"x": "y"}},
            }
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
