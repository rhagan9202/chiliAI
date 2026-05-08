"""Internal transport and workflow models for agent orchestration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now


MetadataValue = str | int | float | bool


def _empty_workflow_steps() -> list[WorkflowStepState]:
    return []


class RetryPolicy(BaseModel):
    """Configuration for coordinator retry-with-backoff behavior."""

    max_retries: int = Field(default=3, ge=0)
    base_delay_seconds: float = Field(default=1.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)

    def delay_for_attempt(self, attempt: int) -> float:
        """Return the delay before the given retry attempt (1-indexed)."""

        if attempt <= 0:
            return 0.0
        return self.base_delay_seconds * (self.backoff_multiplier ** (attempt - 1))


class HealthSettings(BaseModel):
    """Configuration for the worker health check HTTP endpoint."""

    host: str = "0.0.0.0"
    port: int = Field(default=8001, gt=0)
    degraded_after_seconds: float = Field(default=300.0, gt=0.0)


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
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES: frozenset[WorkflowRunStatus] = frozenset(
    {WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED}
)


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
    steps: list[WorkflowStepState] = Field(default_factory=_empty_workflow_steps)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def _validate_steps(self) -> WorkflowRun:
        if not self.steps:
            raise ValueError("WorkflowRun requires at least one step.")
        step_names = [step.step_name for step in self.steps]
        if len(set(step_names)) != len(step_names):
            raise ValueError("WorkflowRun step names must be unique.")
        return self


class WorkflowRunUpdate(BaseModel):
    """Partial update applied to a persisted ``WorkflowRun``.

    Non-``None`` fields replace the existing value wholesale; ``None`` leaves
    the field unchanged. Callers wanting metadata-merge semantics should
    read-modify-write.
    """

    status: WorkflowRunStatus | None = None
    steps: list[WorkflowStepState] | None = None
    metadata: dict[str, MetadataValue] | None = None


__all__ = [
    "HealthSettings",
    "MetadataValue",
    "RetryPolicy",
    "WorkflowRun",
    "WorkflowRunStatus",
    "WorkflowRunUpdate",
    "WorkflowStepState",
    "WorkflowStepStatus",
    "TERMINAL_RUN_STATUSES",
]