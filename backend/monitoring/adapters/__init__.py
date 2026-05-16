"""Monitoring adapters."""

from __future__ import annotations

from monitoring.adapters.in_memory import (
    InMemoryAlertRepository,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.postgres import (
    PostgresAlertHistoryStore,
    PostgresObservationSource,
    PostgresObservationStore,
)
from monitoring.adapters.protocols import ObservationSourceProtocol, ObservationWriter

__all__ = [
    "InMemoryAlertRepository",
    "InMemoryObservationSource",
    "InMemoryObservationWriter",
    "ObservationSourceProtocol",
    "ObservationWriter",
    "PostgresAlertHistoryStore",
    "PostgresObservationSource",
    "PostgresObservationStore",
]
