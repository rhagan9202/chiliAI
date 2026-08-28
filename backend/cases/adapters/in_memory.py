"""In-memory case repository for tests and local development."""

from __future__ import annotations

from datetime import datetime

from cases.exceptions import CaseConcurrentModificationError, CaseNotFoundError
from cases.models import Case

__all__ = ["InMemoryCaseRepository"]


class InMemoryCaseRepository:
    """A dict-backed ``CaseRepository`` keyed by ``(knowledge_base_id, case_id)``."""

    def __init__(self) -> None:
        self._cases: dict[tuple[str, str], Case] = {}

    def create(self, case: Case) -> Case:
        self._cases.setdefault((case.knowledge_base_id, case.id), case)
        return self._cases[(case.knowledge_base_id, case.id)]

    def get(self, *, knowledge_base_id: str, case_id: str) -> Case | None:
        return self._cases.get((knowledge_base_id, case_id))

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
        priority: str | None = None,
    ) -> tuple[list[Case], int]:
        matches = [
            case
            for case in self._cases.values()
            if case.knowledge_base_id == knowledge_base_id
            and (status is None or case.status == status)
            and (priority is None or case.priority == priority)
        ]
        matches.sort(key=lambda case: (case.updated_at, case.id), reverse=True)
        total = len(matches)
        if limit <= 0 or offset < 0:
            return [], total
        return matches[offset : offset + limit], total

    def update(self, case: Case, *, expected_updated_at: datetime) -> Case:
        key = (case.knowledge_base_id, case.id)
        existing = self._cases.get(key)
        if existing is None:
            raise CaseNotFoundError(case.knowledge_base_id, case.id)
        if existing.updated_at != expected_updated_at:
            raise CaseConcurrentModificationError(case.knowledge_base_id, case.id)
        self._cases[key] = case
        return case

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._cases if key[0] == knowledge_base_id]
        for key in keys:
            del self._cases[key]
        return len(keys)
