"""Identity link repository and review-decision service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable

from auditlog.models import AuditEventCreate
from auditlog.service import AuditLogService
from analytics.identity_resolution.models import (
    IdentityLinkDecisionRecord,
    IdentityLinkDecisionRequest,
    IdentityLinkPage,
    IdentityLinkRecord,
    IdentityLinkRepositoryQuery,
    IdentityLinkReviewState,
)
from events.protocols import EventBus
from events.types import IdentityLinkDecisionRecordedEvent, IdentityLinkDecisionReference
from shared.utils import utc_now


@runtime_checkable
class IdentityLinkRepository(Protocol):
    """Store and query KB-scoped identity links."""

    def upsert_link(self, link: IdentityLinkRecord) -> IdentityLinkRecord: ...

    def get_link(
        self, *, knowledge_base_id: str, link_id: str
    ) -> IdentityLinkRecord | None: ...

    def list_links(self, query: IdentityLinkRepositoryQuery) -> IdentityLinkPage: ...


class InMemoryIdentityLinkRepository:
    """In-memory identity link repository for tests and local development."""

    def __init__(self) -> None:
        self._links: dict[tuple[str, str], IdentityLinkRecord] = {}

    def upsert_link(self, link: IdentityLinkRecord) -> IdentityLinkRecord:
        self._links[(link.knowledge_base_id, link.id)] = link.model_copy(deep=True)
        return link.model_copy(deep=True)

    def get_link(
        self, *, knowledge_base_id: str, link_id: str
    ) -> IdentityLinkRecord | None:
        link = self._links.get((knowledge_base_id, link_id))
        return link.model_copy(deep=True) if link is not None else None

    def list_links(self, query: IdentityLinkRepositoryQuery) -> IdentityLinkPage:
        filtered = [
            link.model_copy(deep=True)
            for link in self._links.values()
            if link.knowledge_base_id == query.knowledge_base_id
            and (
                query.canonical_entity_id is None
                or link.canonical_entity_id == query.canonical_entity_id
            )
            and (
                query.source_entity_id is None
                or link.source_entity_id == query.source_entity_id
            )
            and (query.review_state is None or link.review_state == query.review_state)
        ]
        filtered.sort(key=lambda link: (link.updated_at, link.id), reverse=True)
        total = len(filtered)
        return IdentityLinkPage(
            items=filtered[query.offset : query.offset + query.limit],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )


class IdentityDecisionService:
    """Record steward merge/split decisions against identity links."""

    def __init__(
        self,
        repository: IdentityLinkRepository,
        *,
        event_bus: EventBus | None = None,
        audit_log_service: AuditLogService | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._audit_log_service = audit_log_service
        self._clock = clock

    def record_decision(
        self, request: IdentityLinkDecisionRequest
    ) -> IdentityLinkRecord:
        existing = self._repository.get_link(
            knowledge_base_id=request.knowledge_base_id,
            link_id=request.link_id,
        )
        if existing is None:
            raise KeyError(request.link_id)
        now = self._clock()
        decision_record = IdentityLinkDecisionRecord(
            decision=request.decision,
            actor_user_id=request.actor_user_id,
            comment=_clean_comment(request.comment),
            created_at=now,
        )
        updated = existing.model_copy(
            update={
                "review_state": _state_for_decision(request.decision),
                "decision_history": [*existing.decision_history, decision_record],
                "updated_at": now,
            },
            deep=True,
        )
        stored = self._repository.upsert_link(updated)
        self._publish_decision_event(stored, request)
        self._record_audit_event(existing, stored, request)
        return stored

    def _publish_decision_event(
        self,
        link: IdentityLinkRecord,
        request: IdentityLinkDecisionRequest,
    ) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            IdentityLinkDecisionRecordedEvent(
                correlation_id=request.correlation_id,
                source="identity_resolution",
                occurred_at=link.updated_at,
                decisions=[
                    IdentityLinkDecisionReference(
                        knowledge_base_id=link.knowledge_base_id,
                        link_id=link.id,
                        canonical_entity_id=link.canonical_entity_id,
                        source_entity_id=link.source_entity_id,
                        decision=request.decision,
                        review_state=link.review_state,
                        actor_user_id=request.actor_user_id,
                        score=link.score,
                        confidence=link.confidence,
                    )
                ],
            )
        )

    def _record_audit_event(
        self,
        before: IdentityLinkRecord,
        after: IdentityLinkRecord,
        request: IdentityLinkDecisionRequest,
    ) -> None:
        if self._audit_log_service is None:
            return
        self._audit_log_service.record(
            AuditEventCreate(
                tenant_id=request.tenant_id,
                knowledge_base_id=request.knowledge_base_id,
                occurred_at=after.updated_at,
                actor_user_id=request.actor_user_id,
                actor_email=request.actor_email,
                actor_roles=list(request.actor_roles),
                action=f"identity_link.{request.decision}",
                resource_type="identity_link",
                resource_id=request.link_id,
                before={
                    "review_state": before.review_state,
                    "decision_count": len(before.decision_history),
                },
                after={
                    "review_state": after.review_state,
                    "decision_count": len(after.decision_history),
                },
                correlation_id=request.correlation_id,
                metadata={
                    "canonical_entity_id": after.canonical_entity_id,
                    "source_entity_id": after.source_entity_id,
                    "confidence": after.confidence,
                    "score": after.score,
                },
            )
        )


def _state_for_decision(decision: str) -> IdentityLinkReviewState:
    if decision == "approve_merge":
        return "merged"
    if decision == "reject_merge":
        return "rejected"
    if decision == "split_identity":
        return "split"
    raise ValueError(f"Unsupported identity decision '{decision}'.")


def _clean_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    cleaned = comment.strip()
    return cleaned or None


__all__ = [
    "IdentityDecisionService",
    "IdentityLinkRepository",
    "InMemoryIdentityLinkRepository",
]
