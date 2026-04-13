"""Internal transport and workflow models for agent orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


MetadataValue = str | int | float | bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStepStatus(str, Enum):
    """Lifecycle states for a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowRunStatus(str, Enum):
    """Lifecycle states for a workflow run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepState(BaseModel):
    """A single named step tracked within a workflow run."""

    step_name: str
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    """Tracked state for a workflow orchestrated by the agent module."""

    workflow_id: str
    knowledge_base_id: str
    trigger_event_type: str
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING
    steps: list[WorkflowStepState] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_steps(self) -> WorkflowRun:
        if not self.steps:
            raise ValueError("WorkflowRun requires at least one step.")
        step_names = [step.step_name for step in self.steps]
        if len(set(step_names)) != len(step_names):
            raise ValueError("WorkflowRun step names must be unique.")
        return self


__all__ = [
    "MetadataValue",
    "WorkflowRun",
    "WorkflowRunStatus",
    "WorkflowStepState",
    "WorkflowStepStatus",
]