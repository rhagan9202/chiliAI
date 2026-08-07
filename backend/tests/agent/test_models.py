"""Tests for agent module models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.models import WorkflowRun, WorkflowStepState
from agent.service_models import WorkflowSubmissionRequest


def test_workflow_submission_request_requires_steps() -> None:
    with pytest.raises(ValueError, match="at least one requested step"):
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=[],
        )


def test_workflow_run_requires_unique_step_names() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        WorkflowRun(
            workflow_id="workflow-1",
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            steps=[
                WorkflowStepState(step_name="parse"),
                WorkflowStepState(step_name="parse"),
            ],
        )

def test_workflow_step_state_defaults_attempts_to_zero() -> None:
    assert WorkflowStepState(step_name="enrich").attempts == 0


def test_a_step_serialized_before_attempts_existed_still_loads() -> None:
    """Runs persisted before this field must deserialize.

    `WorkflowRun` is stored whole as JSON (`model_dump_json`), so a run written
    by an older worker has no `attempts` key at all. Without a default that is
    a validation error on read, and every in-flight run becomes unloadable at
    deploy time.
    """
    state = WorkflowStepState.model_validate(
        {"step_name": "enrich", "status": "pending"}
    )

    assert state.attempts == 0


def test_a_whole_run_serialized_before_attempts_existed_still_loads() -> None:
    """The realistic shape: the run, not just one step."""
    run = WorkflowRun.model_validate(
        {
            "workflow_id": "wf-1",
            "knowledge_base_id": "kb-1",
            "trigger_event_type": "documents.uploaded",
            "steps": [{"step_name": "enrich", "status": "pending"}],
        }
    )

    assert run.steps[0].attempts == 0


def test_attempts_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        WorkflowStepState(step_name="enrich", attempts=-1)
