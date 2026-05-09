"""Adapter-level protocols for risk scoring."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.risk.models import RankedRiskEntry, RiskProfile


@runtime_checkable
class RiskSignalSourceProtocol(Protocol):
    """Load risk signals for a specific entity."""

    # TODO(production): Extend with batch loading and real-time signal streaming:
    # - load_profiles(kb_id, entity_ids: list[str]) -> list[RiskProfile]
    # - stream_signals(kb_id) -> AsyncIterator[RiskSignal]
    # Implement production adapters that compute signals from the graph + vectorstore.

    def load_profile(self, *, knowledge_base_id: str, entity_id: str) -> RiskProfile: ...

    def list_ranked_entries(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str | None,
        limit: int,
    ) -> list[RankedRiskEntry]: ...

    def load_historical_score(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
    ) -> float | None: ...


__all__ = [
    "RiskSignalSourceProtocol",
]
