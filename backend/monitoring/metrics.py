"""Prometheus metrics helpers used by the worker pipeline (E10-S09).

The metrics declared here use the default ``prometheus_client`` registry
so the :func:`api.middleware.metrics.metrics_endpoint` exporter emits a
unified payload for HTTP and pipeline data.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram

__all__ = [
    "active_alerts_total",
    "observe_pipeline_stage",
    "pipeline_errors_total",
    "pipeline_stage_duration_seconds",
    "record_pipeline_error",
]


pipeline_stage_duration_seconds: Histogram = Histogram(
    "pipeline_stage_duration_seconds",
    "Wall-clock duration of pipeline stages.",
    ["stage"],
)

pipeline_errors_total: Counter = Counter(
    "pipeline_errors_total",
    "Number of errors raised by pipeline stages.",
    ["stage"],
)

active_alerts_total: Gauge = Gauge(
    "active_alerts_total",
    "Current count of active (unresolved) alerts.",
)


@contextmanager
def observe_pipeline_stage(stage: str) -> Generator[None, None, None]:
    """Time a pipeline stage and record errors if the block raises."""

    start = perf_counter()
    try:
        yield
    except Exception:
        pipeline_errors_total.labels(stage=stage).inc()
        raise
    finally:
        elapsed = perf_counter() - start
        pipeline_stage_duration_seconds.labels(stage=stage).observe(elapsed)


def record_pipeline_error(stage: str) -> None:
    """Increment the pipeline error counter for ``stage``."""

    pipeline_errors_total.labels(stage=stage).inc()
