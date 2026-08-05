"""Tests for SAFE-CMS-003 risk projection read models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from analytics.risk.projections import (
    InMemoryRiskProjectionRepository,
    RiskProjectionLevel,
    RiskProjectionQuery,
    RiskProjectionRow,
    RiskProjectionStatus,
)


BASE_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _row(
    entity_id: str,
    *,
    entity_type: str = "provider",
    score: float = 0.5,
    risk_level: str = "medium",
    status: str = "active",
    typologies: list[str] | None = None,
    scored_at: datetime = BASE_TIME,
) -> RiskProjectionRow:
    return RiskProjectionRow(
        knowledge_base_id="kb-1",
        entity_id=entity_id,
        entity_type=entity_type,
        overall_score=score,
        risk_level=cast(RiskProjectionLevel, risk_level),
        top_typology_ids=typologies or [],
        alert_ids=[f"alert-{entity_id}"],
        case_ids=[f"case-{entity_id}"],
        evidence_pack_ids=[f"evidence-{entity_id}"],
        score_run_id="score-run-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        scored_at=scored_at,
        updated_at=scored_at,
        status=cast(RiskProjectionStatus, status),
    )


def test_projection_repository_upserts_by_kb_and_entity_with_detached_copies() -> None:
    repository = InMemoryRiskProjectionRepository()
    stored = repository.upsert(_row("provider-1", score=0.72))
    replacement = repository.upsert(_row("provider-1", score=0.91, risk_level="high"))

    assert stored.overall_score == 0.72
    assert replacement.overall_score == 0.91
    assert repository.get("kb-1", "provider-1") == replacement

    replacement.alert_ids.append("mutated")
    found = repository.get("kb-1", "provider-1")
    assert found is not None
    assert found.alert_ids == ["alert-provider-1"]


def test_projection_repository_keeps_same_entity_id_independent_across_kbs() -> None:
    repository = InMemoryRiskProjectionRepository()
    repository.upsert(_row("provider-1", score=0.91, risk_level="high"))
    repository.upsert(
        _row("provider-1", score=0.2, risk_level="low").model_copy(
            update={"knowledge_base_id": "kb-2"}
        )
    )

    kb_1_row = repository.get("kb-1", "provider-1")
    kb_2_row = repository.get("kb-2", "provider-1")
    assert kb_1_row is not None
    assert kb_2_row is not None
    assert kb_1_row.overall_score == 0.91
    assert kb_2_row.overall_score == 0.2


def test_projection_repository_lists_ranked_page_with_offset() -> None:
    repository = InMemoryRiskProjectionRepository()
    repository.upsert(_row("provider-low", score=0.1, risk_level="low"))
    repository.upsert(_row("provider-high", score=0.9, risk_level="high"))
    repository.upsert(_row("provider-mid", score=0.5, risk_level="medium"))

    page = repository.list(
        RiskProjectionQuery(knowledge_base_id="kb-1", limit=1, offset=1)
    )

    assert page.total == 3
    assert page.limit == 1
    assert page.offset == 1
    assert [item.entity_id for item in page.items] == ["provider-mid"]


def test_projection_repository_uses_freshness_as_score_tiebreaker() -> None:
    repository = InMemoryRiskProjectionRepository()
    repository.upsert(_row("older", score=0.7, scored_at=BASE_TIME - timedelta(hours=2)))
    repository.upsert(_row("newer", score=0.7, scored_at=BASE_TIME))

    page = repository.list(RiskProjectionQuery(knowledge_base_id="kb-1"))

    assert [item.entity_id for item in page.items] == ["newer", "older"]


def test_projection_repository_filters_by_core_operator_facets() -> None:
    repository = InMemoryRiskProjectionRepository()
    repository.upsert(
        _row(
            "provider-1",
            entity_type="provider",
            score=0.88,
            risk_level="high",
            typologies=["upcoding"],
            status="active",
        )
    )
    repository.upsert(
        _row(
            "beneficiary-1",
            entity_type="beneficiary",
            score=0.86,
            risk_level="high",
            typologies=["identity-mismatch"],
            status="case_open",
        )
    )
    repository.upsert(
        _row(
            "provider-2",
            entity_type="provider",
            score=0.2,
            risk_level="low",
            typologies=["upcoding"],
            status="resolved",
        )
    )

    page = repository.list(
        RiskProjectionQuery(
            knowledge_base_id="kb-1",
            entity_type="provider",
            risk_level="high",
            typology_id="upcoding",
            status="active",
        )
    )

    assert page.total == 1
    assert page.items[0].entity_id == "provider-1"


def test_projection_repository_filters_by_score_age() -> None:
    repository = InMemoryRiskProjectionRepository()
    repository.upsert(
        _row("fresh", score=0.8, scored_at=BASE_TIME - timedelta(hours=2))
    )
    repository.upsert(
        _row("stale", score=0.99, scored_at=BASE_TIME - timedelta(hours=30))
    )

    page = repository.list(
        RiskProjectionQuery(
            knowledge_base_id="kb-1",
            max_score_age_hours=24,
            as_of=BASE_TIME,
        )
    )

    assert page.total == 1
    assert [item.entity_id for item in page.items] == ["fresh"]


def test_projection_row_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _row("provider-1", scored_at=datetime(2026, 8, 2, 12, 0))
