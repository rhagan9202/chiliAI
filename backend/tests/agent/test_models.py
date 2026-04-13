"""Tests for agent module models."""

from __future__ import annotations

import pytest

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