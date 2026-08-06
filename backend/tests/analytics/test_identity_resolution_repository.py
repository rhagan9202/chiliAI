"""Tests for SAFE-CMS-012 identity link persistence and review decisions."""

from __future__ import annotations

from datetime import datetime, timezone


from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEventQuery
from auditlog.service import AuditLogService
from analytics.identity_resolution import (
    IdentityDecisionService,
    IdentityLinkDecisionRequest,
    IdentityLinkRecord,
    IdentityLinkRepositoryQuery,
    InMemoryIdentityLinkRepository,
)
from events.adapters.in_memory import InMemoryEventBus


def _link(link_id: str = "identity_link:kb1:canonical-1:source-1") -> IdentityLinkRecord:
    return IdentityLinkRecord(
        id=link_id,
        knowledge_base_id="kb1",
        canonical_entity_id="canonical:1",
        source_entity_id="source:1",
        relationship_type="resolved_identity",
        confidence="medium",
        score=0.55,
        review_state="steward_review",
        decision_source="identity_resolution.candidate_scoring",
        source_refs=["source-system:a"],
        match_reasons=[
            {
                "field": "source_provider_id",
                "reason": "natural_key_match",
                "score_contribution": 0.55,
            }
        ],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_identity_link_repository_is_kb_scoped_and_defensive() -> None:
    repository = InMemoryIdentityLinkRepository()
    stored = repository.upsert_link(_link())
    repository.upsert_link(
        _link("identity_link:kb2:canonical-1:source-1").model_copy(
            update={"knowledge_base_id": "kb2"},
            deep=True,
        )
    )

    stored.source_refs.append("mutated")
    page = repository.list_links(
        IdentityLinkRepositoryQuery(
            knowledge_base_id="kb1",
            canonical_entity_id="canonical:1",
        )
    )

    assert page.total == 1
    assert [item.id for item in page.items] == ["identity_link:kb1:canonical-1:source-1"]
    assert page.items[0].source_refs == ["source-system:a"]


def test_identity_decision_service_records_merge_and_split_history() -> None:
    repository = InMemoryIdentityLinkRepository()
    service = IdentityDecisionService(
        repository,
        clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    repository.upsert_link(_link())

    approved = service.record_decision(
        IdentityLinkDecisionRequest(
            knowledge_base_id="kb1",
            link_id="identity_link:kb1:canonical-1:source-1",
            decision="approve_merge",
            actor_user_id="steward-1",
            comment="same entity after source review",
        )
    )
    split = service.record_decision(
        IdentityLinkDecisionRequest(
            knowledge_base_id="kb1",
            link_id="identity_link:kb1:canonical-1:source-1",
            decision="split_identity",
            actor_user_id="steward-2",
            comment="source record later corrected",
        )
    )

    assert approved.review_state == "merged"
    assert split.review_state == "split"
    assert [(item.decision, item.actor_user_id) for item in split.decision_history] == [
        ("approve_merge", "steward-1"),
        ("split_identity", "steward-2"),
    ]
    assert split.updated_at == datetime(2026, 1, 2, tzinfo=timezone.utc)


def test_identity_decision_service_publishes_event_and_audit_entry() -> None:
    repository = InMemoryIdentityLinkRepository()
    event_bus = InMemoryEventBus()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    service = IdentityDecisionService(
        repository,
        event_bus=event_bus,
        audit_log_service=audit_service,
        clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    repository.upsert_link(_link())

    service.record_decision(
        IdentityLinkDecisionRequest(
            knowledge_base_id="kb1",
            link_id="identity_link:kb1:canonical-1:source-1",
            decision="approve_merge",
            actor_user_id="steward-1",
            actor_email="steward-1@example.test",
            actor_roles=["data_steward"],
            correlation_id="corr-identity-1",
        )
    )

    assert len(event_bus.published_events) == 1
    event = event_bus.published_events[0]
    assert event.event_type == "identity.link_decision.recorded"
    assert event.correlation_id == "corr-identity-1"
    assert event.decisions[0].decision == "approve_merge"
    assert event.decisions[0].review_state == "merged"
    assert event.decisions[0].canonical_entity_id == "canonical:1"
    page = audit_service.list_events(
        AuditEventQuery(
            knowledge_base_id="kb1",
            action_prefix="identity_link.",
        )
    )
    assert page.total_items == 1
    assert page.items[0].action == "identity_link.approve_merge"
    assert page.items[0].resource_id == "identity_link:kb1:canonical-1:source-1"
    assert page.items[0].metadata["canonical_entity_id"] == "canonical:1"


def test_identity_decision_request_has_no_caller_supplied_tenant() -> None:
    """A steward must not be able to choose the tenant their decision is filed under.

    `IdentityLinkDecisionRequest` used to carry `tenant_id`, defaulted to
    "platform" and populated straight from the request body, so a caller could
    file a merge/split under a tenant no supervisor query would look in. The
    ledger stamps the tenant itself now; this asserts the field is gone rather
    than merely unused.
    """

    assert "tenant_id" not in IdentityLinkDecisionRequest.model_fields
