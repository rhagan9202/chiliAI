"""Adapter-level protocols for risk scoring."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.risk.models import RiskProfile


@runtime_checkable
class RiskSignalSourceProtocol(Protocol):
    """Load risk signals for a specific entity."""

    def load_profile(self, *, knowledge_base_id: str, entity_id: str) -> RiskProfile: ...


__all__ = [
    "RiskSignalSourceProtocol",
]