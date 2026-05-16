"""Monitoring adapters."""

from __future__ import annotations

from monitoring.adapters.in_memory import (
    InMemoryAlertRepository,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.protocols import (
    AlertRepositoryProtocol,
    ObservationSourceProtocol,
    ObservationWriter,
)

__all__ = [
    "AlertRepositoryProtocol",
    "InMemoryAlertRepository",
    "InMemoryObservationSource",
    "InMemoryObservationWriter",
    "ObservationSourceProtocol",
    "ObservationWriter",
]
