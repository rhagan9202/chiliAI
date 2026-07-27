"""Policy intelligence orchestration over a durable repository."""

from __future__ import annotations

from collections.abc import Sequence

from policy.adapters.protocols import PolicyItemRepository
from policy.exceptions import (
    PolicyError,
    PolicyItemAlreadyTriagedError,
    PolicyItemNotFoundError,
)
from policy.models import (
    ACTION_TO_STATUS,
    MatchedValue,
    PolicyCitation,
    PolicyDisposition,
    PolicyItem,
    PolicySeverity,
    PolicyTargetKind,
    TriageAction,
)
from shared.utils import generate_id, utc_now

__all__ = ["PolicyService", "create_policy_service"]


class PolicyService:
    """Upsert rule-generated items and record analyst triage (KB-scoped)."""

    def __init__(self, repository: PolicyItemRepository) -> None:
        self._repository = repository

    def record_match(
        self,
        *,
        knowledge_base_id: str,
        rule_id: str,
        rule_pack_id: str,
        target_kind: PolicyTargetKind,
        target_ref: str,
        title: str,
        severity: PolicySeverity,
        matched_fields: dict[str, MatchedValue],
        citations: list[PolicyCitation],
    ) -> PolicyItem:
        now = utc_now()
        item = PolicyItem(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            rule_id=rule_id,
            rule_pack_id=rule_pack_id,
            target_kind=target_kind,
            target_ref=target_ref,
            title=title,
            severity=severity,
            matched_fields=dict(matched_fields),
            citations=list(citations),
            status="open",
            created_at=now,
            updated_at=now,
        )
        return self._repository.upsert(item)

    def get(self, *, knowledge_base_id: str, item_id: str) -> PolicyItem | None:
        return self._repository.get(knowledge_base_id=knowledge_base_id, item_id=item_id)

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        statuses: Sequence[str] | None = None,
        query: str | None = None,
    ) -> tuple[list[PolicyItem], int]:
        """Page a KB's items, narrowed to any of ``statuses`` and a title ``query``."""
        return self._repository.list(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
            statuses=statuses,
            query=query,
        )

    def count_by_status(self, *, knowledge_base_id: str) -> dict[str, int]:
        """Per-status counts across the whole KB, unaffected by the active filter."""
        return self._repository.count_by_status(knowledge_base_id)

    def triage(
        self,
        *,
        knowledge_base_id: str,
        item_id: str,
        action: TriageAction,
        actor: str,
        note: str | None = None,
        case_id: str | None = None,
    ) -> PolicyItem:
        existing = self._repository.get(
            knowledge_base_id=knowledge_base_id, item_id=item_id
        )
        if existing is None:
            raise PolicyItemNotFoundError(knowledge_base_id, item_id)
        if existing.status != "open":
            raise PolicyItemAlreadyTriagedError(knowledge_base_id, item_id)
        disposition = PolicyDisposition(
            action=action, actor=actor, note=note, decided_at=utc_now(), case_id=case_id
        )
        updated = existing.model_copy(
            update={
                "status": ACTION_TO_STATUS[action],
                "disposition": disposition,
                "updated_at": disposition.decided_at,
            }
        )
        return self._repository.update(updated)

    def link_case(
        self, *, knowledge_base_id: str, item_id: str, case_id: str
    ) -> PolicyItem:
        """Attach a created case to an already-triaged item's disposition.

        Called after an escalate triage has committed, so the case is only ever
        created once the item is durably escalated (prevents orphaned cases)."""
        existing = self._repository.get(
            knowledge_base_id=knowledge_base_id, item_id=item_id
        )
        if existing is None:
            raise PolicyItemNotFoundError(knowledge_base_id, item_id)
        if existing.disposition is None:
            raise PolicyError(
                f"Policy item '{item_id}' has no disposition to link a case to."
            )
        disposition = existing.disposition.model_copy(update={"case_id": case_id})
        updated = existing.model_copy(
            update={"disposition": disposition, "updated_at": utc_now()}
        )
        return self._repository.update(updated)


def create_policy_service(repository: PolicyItemRepository) -> PolicyService:
    """Create the default policy service."""
    return PolicyService(repository)
