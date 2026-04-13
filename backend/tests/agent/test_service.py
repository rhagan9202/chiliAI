"""Tests for the agent service."""

from __future__ import annotations

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.service import create_agent_service
from agent.service_models import WorkflowSubmissionRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import AgentWorkflowStartedEvent


def test_agent_service_starts_workflow_persists_run_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    run_store = InMemoryWorkflowRunStore()
    service = create_agent_service(run_store, event_bus=event_bus)

    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse", "chunk", "extract"],
            metadata={"priority": "high"},
        )
    )

    stored_run = run_store.get_run(response.workflow_id)

    assert response.status.value == "running"
    assert response.step_count == 3
    assert stored_run.workflow_id == response.workflow_id
    assert stored_run.metadata["priority"] == "high"
    assert isinstance(event_bus.published_events[-1], AgentWorkflowStartedEvent)