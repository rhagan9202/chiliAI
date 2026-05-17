"""Entity-metric persistence package (graph metrics over time + current snapshot)."""

from __future__ import annotations

from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.postgres import PostgresEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.metrics.exceptions import MetricsError, MetricsRepositoryError
from analytics.metrics.models import (
    GRAPH_SCOPE_ENTITY_ID,
    METRIC_AVG_DEGREE,
    METRIC_ENTITY_COUNT,
    METRIC_RELATIONSHIP_COUNT,
    EntityMetricSample,
    EntityMetricValue,
)
from analytics.metrics.throttle import MetricsRecomputeThrottle

__all__ = [
    "GRAPH_SCOPE_ENTITY_ID",
    "METRIC_AVG_DEGREE",
    "METRIC_ENTITY_COUNT",
    "METRIC_RELATIONSHIP_COUNT",
    "EntityMetricRepository",
    "EntityMetricSample",
    "EntityMetricValue",
    "InMemoryEntityMetricRepository",
    "MetricsError",
    "MetricsRecomputeThrottle",
    "MetricsRepositoryError",
    "PostgresEntityMetricRepository",
]
