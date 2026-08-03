"""Integration tests for durable explanation-review persistence."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from analytics.explainability.adapters.reviews_postgres import (
    PostgresExplanationReviewRepository,
)
from analytics.explainability.reviews import (
    ExplanationReviewCreate,
    ExplanationReviewQuery,
    ExplanationReviewService,
    ExplanationReviewTarget,
)
from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_KB_ID = "kb-explanation-review-pg"


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping explanation-review integration tests.")
    return url


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert connection_provider is not None
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM explanation_reviews WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM explanation_reviews WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    connection_provider.close()


pytestmark = pytest.mark.integration


def test_upsert_and_list_reviews_newest_first(provider: ConnectionProvider) -> None:
    clock = _Clock(datetime(2026, 8, 3, 18, 0, tzinfo=UTC))
    service = ExplanationReviewService(
        PostgresExplanationReviewRepository(provider),
        clock=clock,
    )

    first = service.record_review(
        _review_request(
            evidence_pack_id="evidence-pack-a",
            target=ExplanationReviewTarget(
                target_type="feature_attribution",
                target_id="feature-risk-score",
            ),
            state="useful",
            comment="  captures the billing-risk driver  ",
        )
    )
    clock.advance(minutes=3)
    second = service.record_review(
        _review_request(
            evidence_pack_id="evidence-pack-a",
            target=ExplanationReviewTarget(
                target_type="narrative_section",
                target_id="section-peer-comparison",
            ),
            state="misleading",
            reasons=["wrong_peer_group"],
            comment="Peer comparison uses the wrong geography.",
        )
    )

    page = service.list_reviews(
        ExplanationReviewQuery(
            knowledge_base_id=_KB_ID,
            evidence_pack_id="evidence-pack-a",
            limit=10,
            offset=0,
        )
    )

    assert page.total == 2
    assert [review.id for review in page.items] == [second.id, first.id]
    assert page.items[1].comment == "captures the billing-risk driver"
    assert page.items[0].reasons == ["wrong_peer_group"]


def test_upsert_refreshes_existing_target_without_resetting_created_at(
    provider: ConnectionProvider,
) -> None:
    clock = _Clock(datetime(2026, 8, 3, 19, 0, tzinfo=UTC))
    service = ExplanationReviewService(
        PostgresExplanationReviewRepository(provider),
        clock=clock,
    )
    target = ExplanationReviewTarget(
        target_type="provenance_reference",
        target_id="claim-source-7",
    )

    created = service.record_review(
        _review_request(
            evidence_pack_id="evidence-pack-update",
            target=target,
            state="useful",
            comment="Confirmed against the source extract.",
        )
    )
    clock.advance(minutes=5)
    updated = service.record_review(
        _review_request(
            evidence_pack_id="evidence-pack-update",
            target=target,
            state="unsupported",
            reasons=["missing_source", "unsupported_claim"],
            comment="Source extract no longer supports the generated claim.",
            actor_user_id="analyst-review-2",
        )
    )

    stored = PostgresExplanationReviewRepository(provider).get_for_target(
        knowledge_base_id=_KB_ID,
        evidence_pack_id="evidence-pack-update",
        target=target,
    )

    assert stored is not None
    assert updated.id == created.id == stored.id
    assert stored.created_at == created.created_at
    assert stored.updated_at == updated.updated_at
    assert stored.update_count == 1
    assert stored.state == "unsupported"
    assert stored.actor_user_id == "analyst-review-2"
    assert stored.reasons == ["missing_source", "unsupported_claim"]


def test_list_reviews_isolates_knowledge_base_and_evidence_pack(
    provider: ConnectionProvider,
) -> None:
    service = ExplanationReviewService(
        PostgresExplanationReviewRepository(provider),
        clock=_Clock(datetime(2026, 8, 3, 20, 0, tzinfo=UTC)),
    )
    target = ExplanationReviewTarget(target_type="narrative", target_id="root")
    expected = service.record_review(
        _review_request(
            evidence_pack_id="evidence-pack-visible",
            target=target,
            state="approved",
        )
    )
    service.record_review(
        _review_request(
            evidence_pack_id="evidence-pack-hidden",
            target=target,
            state="approved",
        )
    )
    service.record_review(
        _review_request(
            knowledge_base_id=_KB_ID + "-other",
            evidence_pack_id="evidence-pack-visible",
            target=target,
            state="approved",
        )
    )

    page = service.list_reviews(
        ExplanationReviewQuery(
            knowledge_base_id=_KB_ID,
            evidence_pack_id="evidence-pack-visible",
            limit=10,
            offset=0,
        )
    )

    assert page.total == 1
    assert [review.id for review in page.items] == [expected.id]


def _review_request(
    *,
    evidence_pack_id: str,
    target: ExplanationReviewTarget,
    state: str,
    knowledge_base_id: str = _KB_ID,
    actor_user_id: str = "analyst-review-1",
    reasons: list[str] | None = None,
    comment: str | None = None,
) -> ExplanationReviewCreate:
    return ExplanationReviewCreate(
        knowledge_base_id=knowledge_base_id,
        evidence_pack_id=evidence_pack_id,
        target=target,
        state=state,  # type: ignore[arg-type]
        actor_user_id=actor_user_id,
        actor_email=f"{actor_user_id}@example.test",
        reasons=reasons or [],  # type: ignore[arg-type]
        comment=comment,
    )


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, *, minutes: int) -> None:
        self._now = self._now + timedelta(minutes=minutes)
