"""Service-boundary models for agent workflow submission."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from agent.models import MetadataValue, WorkflowRunStatus


class WorkflowSubmissionRequest(BaseModel):
    """A caller-supplied workflow submission request."""

    knowledge_base_id: str
    trigger_event_type: str
    requested_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_steps(self) -> WorkflowSubmissionRequest:
        if not self.requested_steps:
            raise ValueError("WorkflowSubmissionRequest requires at least one requested step.")
        if len(set(self.requested_steps)) != len(self.requested_steps):
            raise ValueError("WorkflowSubmissionRequest step names must be unique.")
        return self


class WorkflowSubmissionResponse(BaseModel):
    """Summary returned after creating a workflow run."""

    workflow_id: str
    knowledge_base_id: str
    trigger_event_type: str
    status: WorkflowRunStatus
    step_count: int = Field(ge=1)
    queued_steps: list[str] = Field(default_factory=list)


__all__ = ["WorkflowSubmissionRequest", "WorkflowSubmissionResponse"]