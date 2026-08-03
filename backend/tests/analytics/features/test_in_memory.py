"""Tests for the in-memory feature-value repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from analytics.features.adapters.in_memory import InMemoryFeatureValueRepository
from analytics.features.models import FeatureValueRecord


def _record(
    *,
    knowledge_base_id: str = "kb-1",
    entity_type: str = "provider",
    entity_id: str = "provider-204",
    feature_id: str = "weekly_provider_billing_zscore",
    value: float = 3.25,
    normalized_value: float = 0.82,
    catalog_version: str = "cms-fraud-features-v1",
    transformation_version: str = "peerstats-zscore-v1",
    score_run_id: str | None = "score-run-1",
    observed_at: datetime | None = None,
) -> FeatureValueRecord:
    kwargs: dict[str, object] = {}
    if observed_at is not None:
        kwargs["observed_at"] = observed_at
    return FeatureValueRecord(
        knowledge_base_id=knowledge_base_id,
        entity_type=entity_type,
        entity_id=entity_id,
        feature_id=feature_id,
        value=value,
        normalized_value=normalized_value,
        catalog_version=catalog_version,
        transformation_version=transformation_version,
        source_refs=[
            "entity_derived_signals.weekly_provider_billing",
            "raw_records.claims_feed",
        ],
        score_run_id=score_run_id,
        **kwargs,
    )


def test_upsert_and_list_returns_feature_value_with_lineage() -> None:
    repository = InMemoryFeatureValueRepository()
    record = _record()

    repository.upsert(record)

    values = repository.list_for_entity("kb-1", "provider", "provider-204")
    assert len(values) == 1
    assert values[0].feature_id == "weekly_provider_billing_zscore"
    assert values[0].catalog_version == "cms-fraud-features-v1"
    assert values[0].transformation_version == "peerstats-zscore-v1"
    assert values[0].source_refs == [
        "entity_derived_signals.weekly_provider_billing",
        "raw_records.claims_feed",
    ]
    assert values[0].score_run_id == "score-run-1"


def test_upsert_replaces_existing_record_with_same_stable_key() -> None:
    repository = InMemoryFeatureValueRepository()
    repository.upsert(_record(value=3.25, normalized_value=0.82))

    repository.upsert(_record(value=4.5, normalized_value=0.91))

    values = repository.list_for_entity("kb-1", "provider", "provider-204")
    assert len(values) == 1
    assert values[0].value == 4.5
    assert values[0].normalized_value == 0.91


def test_list_for_entity_filters_and_sorts_deterministically() -> None:
    repository = InMemoryFeatureValueRepository()
    repository.upsert(_record(feature_id="z_feature"))
    repository.upsert(_record(feature_id="a_feature"))
    repository.upsert(_record(knowledge_base_id="kb-other", feature_id="other_kb"))
    repository.upsert(_record(entity_type="claim", entity_id="claim-1", feature_id="other_entity"))

    values = repository.list_for_entity("kb-1", "provider", "provider-204")

    assert [value.feature_id for value in values] == ["a_feature", "z_feature"]


def test_list_for_entity_sorts_same_feature_by_observed_at() -> None:
    repository = InMemoryFeatureValueRepository()
    later = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    earlier = later - timedelta(hours=1)
    repository.upsert(
        _record(
            feature_id="same_feature",
            score_run_id="score-run-later",
            observed_at=later,
        )
    )
    repository.upsert(
        _record(
            feature_id="same_feature",
            score_run_id="score-run-earlier",
            observed_at=earlier,
        )
    )

    values = repository.list_for_entity("kb-1", "provider", "provider-204")

    assert [value.score_run_id for value in values] == [
        "score-run-earlier",
        "score-run-later",
    ]


def test_list_for_entity_sorts_mixed_observed_at_timezone_inputs() -> None:
    repository = InMemoryFeatureValueRepository()
    naive_later = datetime(2026, 8, 2, 12, 0)
    aware_earlier = datetime(2026, 8, 2, 11, 0, tzinfo=timezone.utc)
    repository.upsert(
        _record(
            feature_id="same_feature",
            score_run_id="score-run-later",
            observed_at=naive_later,
        )
    )
    repository.upsert(
        _record(
            feature_id="same_feature",
            score_run_id="score-run-earlier",
            observed_at=aware_earlier,
        )
    )

    values = repository.list_for_entity("kb-1", "provider", "provider-204")

    assert [value.score_run_id for value in values] == [
        "score-run-earlier",
        "score-run-later",
    ]
    assert values[1].observed_at == naive_later.replace(tzinfo=timezone.utc)


def test_delete_by_kb_removes_only_matching_knowledge_base() -> None:
    repository = InMemoryFeatureValueRepository()
    repository.upsert(_record(knowledge_base_id="kb-1", feature_id="a_feature"))
    repository.upsert(_record(knowledge_base_id="kb-1", feature_id="b_feature"))
    repository.upsert(_record(knowledge_base_id="kb-2", feature_id="c_feature"))

    removed = repository.delete_by_kb("kb-1")

    assert removed == 2
    assert repository.list_for_entity("kb-1", "provider", "provider-204") == []
    assert len(repository.list_for_entity("kb-2", "provider", "provider-204")) == 1


@pytest.mark.parametrize("normalized_value", [-0.01, 1.01])
def test_normalized_value_is_bounded(normalized_value: float) -> None:
    with pytest.raises(ValidationError):
        _record(normalized_value=normalized_value)


def test_normalized_value_can_be_absent_for_raw_categorical_features() -> None:
    record = FeatureValueRecord(
        knowledge_base_id="kb-1",
        entity_type="provider",
        entity_id="provider-204",
        feature_id="categorical_feature",
        value="high",
        catalog_version="cms-fraud-features-v1",
        transformation_version="categorical-v1",
    )

    assert record.normalized_value is None
