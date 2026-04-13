"""Tests for the in-memory agent adapter."""

from __future__ import annotations

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowStepState


def test_in_memory_workflow_run_store_returns_seeded_run() -> None:
    run = WorkflowRun(
        workflow_id="workflow-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
    )
    store = InMemoryWorkflowRunStore(runs=[run])

    loaded = store.get_run("workflow-1")

    assert loaded == run