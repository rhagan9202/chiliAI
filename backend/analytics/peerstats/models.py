"""Internal domain models for cross-sectional peer-group statistics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PeerAggregate(BaseModel):
    """One entity's aggregate value for one interval bucket and peer group."""

    entity_id: str
    entity_type: str
    peer_group_key: str
    interval_start: datetime
    aggregate_value: float


class PeerGroupStat(BaseModel):
    """Mean/std of a peer group for one interval bucket."""

    peer_group_key: str
    interval_start: datetime
    mean: float
    std: float = Field(ge=0.0)
    count: int = Field(ge=0)


class DerivedRiskSignal(BaseModel):
    """A peer z-score expressed as a persistable, risk-consumable signal."""

    knowledge_base_id: str
    entity_id: str
    entity_type: str
    metric_name: str
    interval_start: datetime
    peer_group_key: str
    aggregate_value: float
    peer_mean: float
    peer_std: float = Field(ge=0.0)
    z_score: float
    signal_value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    rationale: str
    correlation_id: str


__all__ = [
    "DerivedRiskSignal",
    "PeerAggregate",
    "PeerGroupStat",
]
