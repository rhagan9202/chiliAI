"""Internal transport and workflow models for agent orchestration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import cast

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
    degraded_after_drain_errors: int = Field(default=3, gt=0)


class WorkflowStepStatus(str, Enum):
    """Lifecycle states for a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    # A step whose condition evaluated false. Distinct from COMPLETED, which
    # would claim work was done, and from FAILED, which would claim something
    # went wrong; not running is the correct outcome of a false branch.
    SKIPPED = "skipped"


class WorkflowRunStatus(str, Enum):
    """Lifecycle states for a workflow run."""

    QUEUED = "queued"
    RUNNING = "running"
    # Parked on a human approval gate. Deliberately not terminal: the run is
    # alive and waiting for a person, so stale reconciliation must leave it
    # alone rather than failing it for not progressing.
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES: frozenset[WorkflowRunStatus] = frozenset(
    {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    }
)

# Metadata keys the platform writes onto a run (the service at submission and
# the worker's WorkflowEventTracker as events flow). Idempotency comparison must
# exclude these so a re-submit with the same key is not flagged as conflicting
# just because the tracker has since annotated the run.
SYSTEM_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "correlation_id",
        "publish_error",
        "workflow_started_publish_error",
        "source_event_type",
        "last_event_type",
        "last_error",
        "entity_count",
        "relationship_count",
        "vector_count",
        "reason",
    }
)


class WorkflowStepState(BaseModel):
    """A single named step tracked within a workflow run."""

    step_name: str
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    # A first-class field rather than a `metadata` key (spec decision D1):
    # retry accounting is state the executor reasons about, and burying it in
    # a free-form dict makes it stringly-typed and invisible to validation.
    # Defaulted, so runs persisted before this existed still deserialize —
    # WorkflowRun is stored whole as JSON, so a missing key would otherwise
    # make every in-flight run unloadable at deploy time.
    attempts: int = Field(default=0, ge=0)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    """Tracked state for a workflow orchestrated by the agent module."""

    workflow_id: str
    knowledge_base_id: str
    trigger_event_type: str
    status: WorkflowRunStatus = WorkflowRunStatus.QUEUED
    steps: list[WorkflowStepState] = Field(default_factory=_empty_workflow_steps)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)
    idempotency_key: str | None = None
    # Who asked for this run. The executor dispatches capabilities long after
    # the request returns, and it must authorize as the requesting actor —
    # inventing roles would bypass capability permissions for every
    # workflow-dispatched call, and supplying none would deny all of them.
    #
    # First-class rather than metadata keys: `metadata` is
    # `dict[str, str|int|float|bool]`, which cannot hold a role list without
    # stringly-typed encoding, and this is security-relevant state.
    #
    # Optional so runs persisted before this field deserialize; the executor
    # treats a run with no recorded actor as unauthorized rather than guessing.
    actor_user_id: str | None = None
    actor_roles: list[str] = Field(default_factory=lambda: cast(list[str], []))

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
    updated_at: datetime | None = None
    metadata: dict[str, MetadataValue] | None = None


__all__ = [
    "HealthSettings",
    "MetadataValue",
    "RetryPolicy",
    "SYSTEM_METADATA_KEYS",
    "WorkflowRun",
    "WorkflowRunStatus",
    "WorkflowRunUpdate",
    "WorkflowStepState",
    "WorkflowStepStatus",
    "TERMINAL_RUN_STATUSES",
]
