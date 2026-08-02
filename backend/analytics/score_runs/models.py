"""Models for durable score-all run tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared.utils import utc_now

ScoreRunStatus = Literal["queued", "running", "completed", "failed", "canceled", "replayed"]
ScoreBatchStatus = Literal["queued", "running", "completed", "failed", "canceled", "replayed"]


class ScoreRun(BaseModel):
    """Durable state for one KB-scoped score-all run."""

    id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    status: ScoreRunStatus = "queued"
    requested_by: str | None = None
    idempotency_key: str | None = None
    model_version: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    replay_of_run_id: str | None = None
    total_entities: int = Field(default=0, ge=0)
    scored_entities: int = Field(default=0, ge=0)
    failed_entities: int = Field(default=0, ge=0)
    error_summary: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_counts(self) -> ScoreRun:
        if self.scored_entities + self.failed_entities > self.total_entities:
            raise ValueError("ScoreRun scored_entities + failed_entities cannot exceed total_entities.")
        if self.finished_at is not None and self.started_at is not None and self.finished_at < self.started_at:
            raise ValueError("ScoreRun finished_at cannot be before started_at.")
        return self


class ScoreBatch(BaseModel):
    """Durable state for one batch inside a score-all run."""

    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    batch_number: int = Field(ge=0)
    status: ScoreBatchStatus = "queued"
    entity_ids: list[str] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0)
    error_summary: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_batch(self) -> ScoreBatch:
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise ValueError("ScoreBatch entity_ids must be unique.")
        if self.finished_at is not None and self.started_at is not None and self.finished_at < self.started_at:
            raise ValueError("ScoreBatch finished_at cannot be before started_at.")
        return self


__all__ = [
    "ScoreBatch",
    "ScoreBatchStatus",
    "ScoreRun",
    "ScoreRunStatus",
]
