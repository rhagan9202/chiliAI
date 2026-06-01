"""Case management orchestration over a durable repository."""

from __future__ import annotations

from cases.adapters.protocols import CaseRepository
from cases.exceptions import CaseNotFoundError
from cases.models import Case, CasePriority, CaseStatus, CaseTimelineEvent
from shared.types import Alert
from shared.utils import generate_id, utc_now

__all__ = ["CaseService", "create_case_service"]

_SEVERITY_TO_PRIORITY: dict[str, CasePriority] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


class CaseService:
    """Create, read, update, and promote investigation cases (KB-scoped)."""

    def __init__(self, repository: CaseRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        knowledge_base_id: str,
        title: str,
        priority: CasePriority,
        assignee: str | None = None,
        alert_ids: list[str] | None = None,
    ) -> Case:
        case = Case(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            title=title,
            status="open",
            priority=priority,
            assignee=assignee,
            alert_ids=list(alert_ids or []),
        )
        return self._repository.create(case)

    def get(self, *, knowledge_base_id: str, case_id: str) -> Case | None:
        return self._repository.get(knowledge_base_id=knowledge_base_id, case_id=case_id)

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: str | None = None,
        priority: str | None = None,
    ) -> tuple[list[Case], int]:
        return self._repository.list(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
            status=status,
            priority=priority,
        )

    def update(
        self,
        *,
        knowledge_base_id: str,
        case_id: str,
        title: str | None = None,
        status: CaseStatus | None = None,
        priority: CasePriority | None = None,
        assignee: str | None = None,
    ) -> Case:
        existing = self._repository.get(
            knowledge_base_id=knowledge_base_id, case_id=case_id
        )
        if existing is None:
            raise CaseNotFoundError(knowledge_base_id, case_id)

        changes: dict[str, object] = {"updated_at": utc_now()}
        if title is not None:
            changes["title"] = title
        if status is not None:
            changes["status"] = status
        if priority is not None:
            changes["priority"] = priority
        if assignee is not None:
            changes["assignee"] = assignee
        return self._repository.update(existing.model_copy(update=changes))

    def promote_from_alert(
        self,
        *,
        knowledge_base_id: str,
        alert: Alert,
        evidence_pack_id: str | None = None,
        timeline: list[CaseTimelineEvent] | None = None,
        notes: str | None = None,
    ) -> Case:
        """Promote an alert into a new case, capturing its evidence + timeline."""
        title = f"Investigation: {alert.title}"
        if notes:
            title = f"{title} — {notes}"
        case = Case(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            title=title,
            status="open",
            priority=_severity_to_priority(alert.severity),
            originating_alert_id=alert.id,
            evidence_pack_id=evidence_pack_id or alert.evidence_pack_id,
            alert_ids=[alert.id],
            timeline=list(timeline or []),
        )
        return self._repository.create(case)


def _severity_to_priority(severity: str) -> CasePriority:
    return _SEVERITY_TO_PRIORITY.get(severity.strip().lower(), "medium")


def create_case_service(repository: CaseRepository) -> CaseService:
    """Create the default case service."""
    return CaseService(repository)
