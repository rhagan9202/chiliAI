"""In-memory risk signal source for tests and local development."""

from __future__ import annotations

from analytics.risk.models import RiskProfile


class InMemoryRiskSignalSource:
    """A seeded source of risk profiles keyed by knowledge base and entity."""

    def __init__(self, profiles: list[RiskProfile] | None = None) -> None:
        self._profiles: dict[tuple[str, str], RiskProfile] = {}
        for profile in profiles or []:
            self.put_profile(profile)

    def put_profile(self, profile: RiskProfile) -> None:
        self._profiles[(profile.knowledge_base_id, profile.entity_id)] = profile

    def load_profile(self, *, knowledge_base_id: str, entity_id: str) -> RiskProfile:
        profile = self._profiles.get((knowledge_base_id, entity_id))
        if profile is None:
            raise ValueError(
                f"No risk profile registered for knowledge_base_id='{knowledge_base_id}' and entity_id='{entity_id}'."
            )
        return profile