"""Tests for SAFE-CMS-003 risk projection writer service."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.features.models import FeatureValueRecord
from analytics.risk.projection_service import (
    RiskProjectionService,
    RiskProjectionWriteRequest,
)
from analytics.risk.projections import InMemoryRiskProjectionRepository, RiskProjectionRow
from events.types import RiskFactorReference, RiskScoredReference


BASE_TIME = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)


def _assessment(entity_id: str = "provider:123") -> RiskScoredReference:
    return RiskScoredReference(
        knowledge_base_id="kb-1",
        request_id="risk:run-1:batch-0:provider:123",
        entity_id=entity_id,
        overall_score=0.91,
        risk_level="high",
        factor_count=1,
        factors=[
            RiskFactorReference(
                factor_name="billing_outlier",
                raw_value=0.95,
                weight=1.0,
                contribution=0.91,
                rationale="Provider billing is above peer norm.",
            )
        ],
    )


def _feature(feature_id: str = "billing_outlier") -> FeatureValueRecord:
    return FeatureValueRecord(
        knowledge_base_id="kb-1",
        entity_type="provider",
        entity_id="provider:123",
        feature_id=feature_id,
        normalized_value=0.95,
        catalog_version="cms-fraud-features-v1",
        transformation_version="transform-v1",
        observed_at=BASE_TIME,
        score_run_id="score-run-1",
    )


def _request() -> RiskProjectionWriteRequest:
    return RiskProjectionWriteRequest(
        assessment=_assessment(),
        entity_type="provider",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        score_run_id="score-run-1",
        scored_at=BASE_TIME,
        feature_values=[_feature()],
        feature_typology_index={"billing_outlier": ["upcoding", "medically_unlikely"]},
        alert_ids=["alert-1"],
        case_ids=["case-1"],
        evidence_pack_ids=["evidence-1"],
        status="case_open",
    )


def test_project_assessment_writes_projection_with_versions_and_refs() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)

    result = service.project_assessment(_request())

    assert result.changed is True
    assert result.created is True
    assert result.row.entity_id == "provider:123"
    assert result.row.entity_type == "provider"
    assert result.row.overall_score == 0.91
    assert result.row.risk_level == "high"
    assert result.row.top_typology_ids == ["medically_unlikely", "upcoding"]
    assert result.row.alert_ids == ["alert-1"]
    assert result.row.case_ids == ["case-1"]
    assert result.row.evidence_pack_ids == ["evidence-1"]
    assert result.row.score_run_id == "score-run-1"
    assert result.row.model_version == "risk-linear-v1"
    assert result.row.catalog_version == "cms-fraud-features-v1"
    assert result.row.scored_at == BASE_TIME
    assert repository.get("kb-1", "provider:123") == result.row


def test_project_assessment_is_noop_when_projection_is_unchanged() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    request = _request()

    first = service.project_assessment(request)
    second = service.project_assessment(request)

    assert first.changed is True
    assert second.changed is False
    assert second.created is False
    assert second.row == first.row


def test_project_assessment_ignores_feature_values_from_other_entities() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    request = _request().model_copy(
        update={
            "feature_values": [
                _feature(),
                _feature("identity_mismatch").model_copy(
                    update={"entity_id": "beneficiary:999", "entity_type": "beneficiary"}
                ),
            ],
            "feature_typology_index": {
                "billing_outlier": ["upcoding"],
                "identity_mismatch": ["identity"],
            },
        },
        deep=True,
    )

    result = service.project_assessment(request)

    assert result.row.top_typology_ids == ["upcoding"]


def test_project_assessment_maps_scored_factors_to_typologies_without_feature_values() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    request = _request().model_copy(
        update={
            "feature_values": [],
            "feature_typology_index": {
                "billing_outlier": ["upcoding"],
                "unscored_feature": ["volume"],
            },
        },
        deep=True,
    )

    result = service.project_assessment(request)

    assert result.row.top_typology_ids == ["upcoding"]


def test_project_assessment_does_not_overwrite_newer_projection_with_stale_score() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    newer = _request().model_copy(
        update={"scored_at": datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)},
        deep=True,
    )
    older = _request().model_copy(
        update={
            "scored_at": BASE_TIME,
            "assessment": _assessment().model_copy(
                update={"request_id": "risk:older", "overall_score": 0.12, "risk_level": "low"}
            ),
        },
        deep=True,
    )

    first = service.project_assessment(newer)
    stale = service.project_assessment(older)

    assert first.changed is True
    assert stale.changed is False
    assert stale.row == first.row
    assert repository.get("kb-1", "provider:123") == first.row


def test_project_assessment_preserves_timestamp_for_same_score_run_republish() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    first = service.project_assessment(_request()).row
    republished = _request().model_copy(
        update={
            "scored_at": datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc),
            "alert_ids": ["alert-2"],
        },
        deep=True,
    )

    result = service.project_assessment(republished)

    assert result.changed is True
    assert result.row.score_run_id == first.score_run_id
    assert result.row.scored_at == first.scored_at
    assert result.row.updated_at == first.updated_at
    assert result.row.alert_ids == ["alert-2"]


def test_project_assessment_ignores_feature_values_with_wrong_entity_type_or_unscored_feature() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    request = _request().model_copy(
        update={
            "feature_values": [
                _feature(),
                _feature("wrong_type_feature").model_copy(update={"entity_type": "beneficiary"}),
                _feature("unscored_feature"),
            ],
            "feature_typology_index": {
                "billing_outlier": ["upcoding"],
                "wrong_type_feature": ["identity"],
                "unscored_feature": ["volume"],
            },
        },
        deep=True,
    )

    result = service.project_assessment(request)

    assert result.row.top_typology_ids == ["upcoding"]


def test_rebuild_knowledge_base_is_noop_for_unchanged_rows() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    row = service.project_assessment(_request()).row

    result = service.rebuild_knowledge_base("kb-1", [row])

    assert result.changed is False
    assert result.deleted == 0
    assert result.upserted == 0


def test_rebuild_knowledge_base_compares_all_rows_beyond_query_page_limit() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    rows = [
        RiskProjectionRow(
            knowledge_base_id="kb-1",
            entity_id=f"provider:{index}",
            entity_type="provider",
            overall_score=0.1,
            risk_level="low",
            model_version="risk-linear-v1",
            catalog_version="cms-fraud-features-v1",
            scored_at=BASE_TIME,
        )
        for index in range(501)
    ]
    for row in rows:
        repository.upsert(row)

    result = service.rebuild_knowledge_base("kb-1", rows[:-1])

    assert result.changed is True
    assert result.deleted == 501
    assert result.upserted == 500
    assert repository.get("kb-1", "provider:500") is None


def test_rebuild_knowledge_base_preserves_other_kbs() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    row = service.project_assessment(_request()).row
    other_kb_row = row.model_copy(
        update={"knowledge_base_id": "kb-2", "overall_score": 0.2, "risk_level": "low"}
    )
    repository.upsert(other_kb_row)

    result = service.rebuild_knowledge_base("kb-1", [])

    assert result.changed is True
    assert result.deleted == 1
    assert repository.get("kb-1", "provider:123") is None
    assert repository.get("kb-2", "provider:123") == other_kb_row


def test_rebuild_knowledge_base_replaces_stale_rows() -> None:
    repository = InMemoryRiskProjectionRepository()
    service = RiskProjectionService(repository)
    stale = service.project_assessment(_request()).row
    replacement = RiskProjectionRow(
        **stale.model_copy(
            update={
                "entity_id": "provider:456",
                "overall_score": 0.44,
                "risk_level": "low",
            }
        ).model_dump()
    )

    result = service.rebuild_knowledge_base("kb-1", [replacement])

    assert result.changed is True
    assert result.deleted == 1
    assert result.upserted == 1
    assert repository.get("kb-1", "provider:123") is None
    assert repository.get("kb-1", "provider:456") == replacement
