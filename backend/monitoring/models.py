"""Internal transport and workflow models for active monitoring."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MonitoringObservation(BaseModel):
    """A scored observation produced by upstream monitoring inputs."""

    entity_id: str
    entity_type: str
    metric_name: str
    score: float = Field(ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=_utc_now)
    rationale: str
    evidence_pack_id: str | None = None


class MonitoringBatch(BaseModel):
    """A batch of monitoring observations for one knowledge base."""

    knowledge_base_id: str
    batch_id: str
    observations: list[MonitoringObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_observations(self) -> MonitoringBatch:
        if not self.observations:
            raise ValueError("MonitoringBatch requires at least one observation.")
        return self


class AlertCandidate(BaseModel):
    """An internal candidate ready to become a surfaced alert."""

    entity_id: str
    entity_type: str
    severity: str
    title: str
    reasoning: str
    score: float = Field(ge=0.0, le=1.0)
    evidence_pack_id: str | None = None


__all__ = ["AlertCandidate", "MonitoringBatch", "MonitoringObservation"]