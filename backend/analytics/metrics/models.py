"""Internal models for entity-metric persistence."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import utc_now

GRAPH_SCOPE_ENTITY_ID = "__graph__"
"""Sentinel entity id for graph-wide (KB-level) metrics that have no single owner."""

METRIC_ENTITY_COUNT = "entity_count"
METRIC_RELATIONSHIP_COUNT = "relationship_count"
METRIC_AVG_DEGREE = "avg_degree"


class EntityMetricSample(BaseModel):
    """One metric value for one entity (or graph scope) at a point in time."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    value: float
    observed_at: datetime = Field(default_factory=utc_now)
    correlation_id: str


class EntityMetricValue(BaseModel):
    """The latest value of one metric for one entity (current snapshot)."""

    knowledge_base_id: str
    entity_id: str
    metric_name: str
    value: float
    updated_at: datetime


__all__ = [
    "GRAPH_SCOPE_ENTITY_ID",
    "METRIC_AVG_DEGREE",
    "METRIC_ENTITY_COUNT",
    "METRIC_RELATIONSHIP_COUNT",
    "EntityMetricSample",
    "EntityMetricValue",
]
