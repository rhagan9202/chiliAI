"""Adapter-level protocols for monitoring inputs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from monitoring.models import MonitoringBatch


@runtime_checkable
class ObservationSourceProtocol(Protocol):
    """Load a monitoring batch for evaluation."""

    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch: ...


__all__ = [
    "ObservationSourceProtocol",
]