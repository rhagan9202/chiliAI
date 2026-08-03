from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

import pytest

from analytics.explainability.reviews import (
    ExplanationReviewCreate,
    ExplanationReviewQuery,
    ExplanationReviewService,
    ExplanationReviewTarget,
    InMemoryExplanationReviewRepository,
)


def _clock() -> tuple[Callable[[], datetime], list[datetime]]:
    values = [
        datetime(2026, 8, 3, 14, 0, tzinfo=UTC),
        datetime(2026, 8, 3, 14, 5, tzinfo=UTC),
        datetime(2026, 8, 3, 14, 10, tzinfo=UTC),
    ]

    def now() -> datetime:
        return values.pop(0)

    return now, values


def test_negative_review_requires_structured_reason() -> None:
    service = ExplanationReviewService(InMemoryExplanationReviewRepository())

    with pytest.raises(ValueError, match="reason"):
        service.record_review(
            ExplanationReviewCreate(
                knowledge_base_id="kb-1",
                evidence_pack_id="evidence-1",
                target=ExplanationReviewTarget(
                    target_type="narrative",
                    target_id="summary",
                ),
                state="unsupported",
                actor_user_id="analyst-42",
            )
        )


def test_create_review_trims_comment_and_lists_newest_first() -> None:
    now, _ = _clock()
    service = ExplanationReviewService(
        InMemoryExplanationReviewRepository(),
        clock=now,
    )

    useful = service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id="kb-1",
            evidence_pack_id="evidence-1",
            target=ExplanationReviewTarget(
                target_type="feature_attribution",
                target_id="peer_deviation",
            ),
            state="useful",
            actor_user_id="analyst-42",
            actor_email="analyst42@example.test",
            comment="  Clear link to peer deviation.  ",
        )
    )
    incomplete = service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id="kb-1",
            evidence_pack_id="evidence-1",
            target=ExplanationReviewTarget(
                target_type="narrative_section",
                target_id="section:0:Billing Pattern",
            ),
            state="incomplete",
            reasons=["missing_source"],
            actor_user_id="analyst-43",
        )
    )

    page = service.list_reviews(
        ExplanationReviewQuery(knowledge_base_id="kb-1", evidence_pack_id="evidence-1")
    )

    assert [item.id for item in page.items] == [incomplete.id, useful.id]
    assert page.total == 2
    assert useful.comment == "Clear link to peer deviation."
    assert useful.created_at == datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
    assert incomplete.created_at == datetime(2026, 8, 3, 14, 5, tzinfo=UTC)


def test_update_same_target_preserves_created_at_and_advances_updated_at() -> None:
    now, _ = _clock()
    service = ExplanationReviewService(
        InMemoryExplanationReviewRepository(),
        clock=now,
    )

    created = service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id="kb-1",
            evidence_pack_id="evidence-1",
            target=ExplanationReviewTarget(
                target_type="narrative",
                target_id="summary",
            ),
            state="useful",
            actor_user_id="analyst-42",
        )
    )
    updated = service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id="kb-1",
            evidence_pack_id="evidence-1",
            target=ExplanationReviewTarget(
                target_type="narrative",
                target_id="summary",
            ),
            state="misleading",
            reasons=["wrong_peer_group"],
            actor_user_id="analyst-42",
            comment="Uses a non-comparable cohort.",
        )
    )

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at == created.created_at + timedelta(minutes=5)
    assert updated.state == "misleading"
    assert updated.reasons == ["wrong_peer_group"]
    assert updated.update_count == 1


def test_queries_do_not_leak_between_knowledge_bases_or_evidence_packs() -> None:
    now, _ = _clock()
    service = ExplanationReviewService(
        InMemoryExplanationReviewRepository(),
        clock=now,
    )

    for knowledge_base_id, evidence_pack_id in [
        ("kb-1", "evidence-1"),
        ("kb-1", "evidence-2"),
        ("kb-2", "evidence-1"),
    ]:
        service.record_review(
            ExplanationReviewCreate(
                knowledge_base_id=knowledge_base_id,
                evidence_pack_id=evidence_pack_id,
                target=ExplanationReviewTarget(
                    target_type="narrative",
                    target_id="summary",
                ),
                state="useful",
                actor_user_id="analyst-42",
            )
        )

    page = service.list_reviews(
        ExplanationReviewQuery(knowledge_base_id="kb-1", evidence_pack_id="evidence-1")
    )

    assert page.total == 1
    assert page.items[0].knowledge_base_id == "kb-1"
    assert page.items[0].evidence_pack_id == "evidence-1"
