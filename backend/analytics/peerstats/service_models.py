"""Service-boundary models for peerstats compute requests/responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from config.schema import PeerMetricSpec


class PeerStatsComputeRequest(BaseModel):
    """A request to compute peer z-scores for one spec over given intervals."""

    knowledge_base_id: str
    spec: PeerMetricSpec
    interval_starts: list[datetime] = Field(default_factory=list[datetime])
    correlation_id: str


class PeerStatsComputeResponse(BaseModel):
    """The outcome of one peerstats compute call."""

    metric_name: str
    signals_written: int = Field(ge=0)
    affected_entity_ids: list[str] = Field(default_factory=list[str])


__all__ = ["PeerStatsComputeRequest", "PeerStatsComputeResponse"]
