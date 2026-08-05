"""Case management orchestration over a durable repository."""

from __future__ import annotations

from cases.adapters.protocols import CaseRepository
from cases.exceptions import AlertAlreadyAttachedError, CaseNotFoundError
from cases.models import (
    AnalystFeedback,
    Case,
    CasePriority,
    CaseStatus,
    CaseTimelineEvent,
    EvidenceAdequacy,
    FeedbackLabel,
)
from playbooks.models import PlaybookRef
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
        timeline: list[CaseTimelineEvent] | None = None,
        playbook_ref: PlaybookRef | None = None,
    ) -> Case:
        case = Case(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            title=title,
            status="open",
            priority=priority,
            assignee=assignee,
            playbook_ref=playbook_ref,
            alert_ids=list(alert_ids or []),
            timeline=list(timeline or []),
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

    def add_feedback(
        self,
        *,
        knowledge_base_id: str,
        case_id: str,
        label: FeedbackLabel,
        evidence_adequacy: EvidenceAdequacy,
        missing_evidence: list[str],
        notes: str,
    ) -> Case:
        existing = self._repository.get(
            knowledge_base_id=knowledge_base_id, case_id=case_id
        )
        if existing is None:
            raise CaseNotFoundError(knowledge_base_id, case_id)

        feedback = AnalystFeedback(
            case_id=case_id,
            label=label,
            evidence_adequacy=evidence_adequacy,
            missing_evidence=list(missing_evidence),
            notes=notes,
        )
        return self._repository.update(
            existing.model_copy(
                update={
                    "feedback_history": [*existing.feedback_history, feedback],
                    "updated_at": utc_now(),
                }
            )
        )

    def attach_alert(
        self,
        *,
        knowledge_base_id: str,
        case_id: str,
        alert: Alert,
        notes: str | None = None,
    ) -> Case:
        """Add an alert to a case that already exists (UXA-405).

        The workflow ``promote_from_alert`` cannot express: promote opens a
        *new* case, and nothing could add to an existing one. ``evidence_pack_id``
        is deliberately left alone — it records what the case was opened from,
        and repointing it here would silently rewrite the case's origin. The
        attached alert's own pack stays reachable through the alert.
        """
        existing = self._repository.get(
            knowledge_base_id=knowledge_base_id, case_id=case_id
        )
        if existing is None:
            raise CaseNotFoundError(knowledge_base_id, case_id)
        if alert.id in existing.alert_ids:
            raise AlertAlreadyAttachedError(case_id, alert.id)

        detail = f"{alert.title} ({alert.severity})"
        if notes:
            detail = f"{detail} — {notes}"
        event = CaseTimelineEvent(
            occurred_at=utc_now(), label="Alert attached", detail=detail
        )
        return self._repository.update(
            existing.model_copy(
                update={
                    "alert_ids": [*existing.alert_ids, alert.id],
                    "timeline": [*existing.timeline, event],
                    "updated_at": event.occurred_at,
                }
            )
        )

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
            playbook_ref=_playbook_ref_from_alert(alert),
            alert_ids=[alert.id],
            timeline=list(timeline or []),
        )
        return self._repository.create(case)


def _severity_to_priority(severity: str) -> CasePriority:
    return _SEVERITY_TO_PRIORITY.get(severity.strip().lower(), "medium")


def _playbook_ref_from_alert(alert: Alert) -> PlaybookRef | None:
    raw_ref = alert.generation_metadata.get("playbook_ref")
    if raw_ref is None:
        return None
    if isinstance(raw_ref, PlaybookRef):
        return raw_ref
    if not isinstance(raw_ref, dict):
        return None
    try:
        return PlaybookRef.model_validate(raw_ref)
    except ValueError:
        return None


def create_case_service(repository: CaseRepository) -> CaseService:
    """Create the default case service."""
    return CaseService(repository)
