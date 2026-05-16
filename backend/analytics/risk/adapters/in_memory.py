"""In-memory risk signal source for tests and local development."""

from __future__ import annotations

from analytics.risk.models import RankedRiskEntry, RiskAssessmentRecord, RiskProfile

__all__ = ["InMemoryRiskHistoryWriter", "InMemoryRiskSignalSource"]


class InMemoryRiskSignalSource:
    """A seeded source of risk profiles keyed by knowledge base and entity."""

    def __init__(
        self,
        profiles: list[RiskProfile] | None = None,
        *,
        ranked_entries: list[RankedRiskEntry] | None = None,
        historical_scores: dict[tuple[str, str], float] | None = None,
    ) -> None:
        self._profiles: dict[tuple[str, str], RiskProfile] = {}
        self._ranked_entries: list[RankedRiskEntry] = list(ranked_entries or [])
        self._historical_scores: dict[tuple[str, str], float] = dict(historical_scores or {})
        for profile in profiles or []:
            self.put_profile(profile)

    def put_profile(self, profile: RiskProfile) -> None:
        self._profiles[(profile.knowledge_base_id, profile.entity_id)] = profile

    def put_ranked_entry(self, entry: RankedRiskEntry) -> None:
        self._ranked_entries.append(entry)

    def put_historical_score(
        self, *, knowledge_base_id: str, entity_id: str, score: float
    ) -> None:
        self._historical_scores[(knowledge_base_id, entity_id)] = score

    def load_profile(self, *, knowledge_base_id: str, entity_id: str) -> RiskProfile:
        profile = self._profiles.get((knowledge_base_id, entity_id))
        if profile is None:
            raise ValueError(
                f"No risk profile registered for knowledge_base_id='{knowledge_base_id}' and entity_id='{entity_id}'."
            )
        return profile

    def list_ranked_entries(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str | None,
        limit: int,
    ) -> list[RankedRiskEntry]:
        filtered = [
            entry
            for entry in self._ranked_entries
            if entry.knowledge_base_id == knowledge_base_id
            and (entity_type is None or entry.entity_type == entity_type)
        ]
        filtered.sort(key=lambda entry: entry.overall_score, reverse=True)
        return filtered[:limit]

    def load_historical_score(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
    ) -> float | None:
        return self._historical_scores.get((knowledge_base_id, entity_id))


class InMemoryRiskHistoryWriter:
    """A ``RiskHistoryWriter`` that records assessments in memory."""

    def __init__(self) -> None:
        self._records: dict[str, RiskAssessmentRecord] = {}

    def write_assessment(self, record: RiskAssessmentRecord) -> bool:
        if record.request_id in self._records:
            return False
        self._records[record.request_id] = record
        return True

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
        ]
        if not matches:
            return None
        latest = max(matches, key=lambda record: record.assessed_at)
        return latest.overall_score
