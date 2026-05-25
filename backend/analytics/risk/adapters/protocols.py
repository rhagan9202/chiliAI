"""Adapter-level protocols for risk scoring."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from analytics.risk.models import RankedRiskEntry, RiskAssessmentRecord, RiskProfile


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


@runtime_checkable
class RiskHistoryWriter(Protocol):
    """Persist risk assessments to the ``risk_score_history`` log.

    The Postgres implementation also exposes a latest-score read so Flow 3
    closes its own loop; full ``RiskSignalSourceProtocol`` backing is out of
    scope (signals are graph-derived — see design section 1).
    """

    def write_assessment(self, record: RiskAssessmentRecord) -> bool:
        """Persist one assessment idempotently; return True if a row was written."""
        ...

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        """Return the most recent overall risk score for one entity, if any."""
        ...


__all__ = [
    "RiskHistoryWriter",
    "RiskSignalSourceProtocol",
]
