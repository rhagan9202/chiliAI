"""Monitoring adapters."""

from __future__ import annotations

from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.adapters.protocols import ObservationSourceProtocol

__all__ = ["InMemoryObservationSource", "ObservationSourceProtocol"]