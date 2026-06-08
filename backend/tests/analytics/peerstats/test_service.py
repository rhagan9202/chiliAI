"""Tests for PeerStatsService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.exceptions import PeerStatsSourceError
from analytics.peerstats.models import PeerAggregate
from analytics.peerstats.service import PeerStatsService, create_peerstats_service
from analytics.peerstats.service_models import PeerStatsComputeRequest
from config.schema import PeerMetricSpec

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _spec(**overrides: object) -> PeerMetricSpec:
    base: dict[str, object] = dict(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
        min_peers=2,
        z_cap=4.0,
        direction="high",
    )
    base.update(overrides)
    return PeerMetricSpec(**base)  # type: ignore[arg-type]


def _seed(source: InMemoryRecordColumnSource, values: dict[str, float]) -> None:
    rows = [
        ColumnRow(entity_id=eid, entity_type="provider", group_values=(),
                  value=v, observed_at=MONDAY)
        for eid, v in values.items()
    ]
    source.add_rows("kb1", "claim_record", rows)


def _service(
    source: InMemoryRecordColumnSource, writer: InMemoryDerivedRiskSignalWriter
) -> PeerStatsService:
    return create_peerstats_service(source, writer=writer)


def test_compute_writes_one_signal_per_entity_with_correct_z() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    # values [1, 1, 1, 5]: mean=2.0, pop std=sqrt(3)=1.732..., z(5)=1.732
    _seed(source, {"provider:1": 1.0, "provider:2": 1.0, "provider:3": 1.0, "provider:4": 5.0})
    response = _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(), interval_starts=[MONDAY],
            correlation_id="c1",
        )
    )
    assert response.signals_written == 4
    assert set(response.affected_entity_ids) == {f"provider:{i}" for i in range(1, 5)}
    outlier = writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:4")[0]
    assert round(outlier.z_score, 3) == 1.732
    assert round(outlier.signal_value, 4) == round(1.732 / 4.0, 4)


def test_cohort_below_min_peers_is_skipped() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    _seed(source, {"provider:1": 10.0})  # only 1 peer
    response = _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(min_peers=5),
            interval_starts=[MONDAY], correlation_id="c1",
        )
    )
    assert response.signals_written == 0
    assert response.affected_entity_ids == []


def test_zero_std_yields_zero_z_and_signal() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    _seed(source, {"provider:1": 4.0, "provider:2": 4.0, "provider:3": 4.0})
    _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(), interval_starts=[MONDAY],
            correlation_id="c1",
        )
    )
    signal = writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:1")[0]
    assert signal.z_score == 0.0
    assert signal.signal_value == 0.0


def test_compute_handles_multiple_intervals() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    tuesday_next = datetime(2026, 1, 13, tzinfo=timezone.utc)  # week of Jan 12
    week2_start = datetime(2026, 1, 12, tzinfo=timezone.utc)
    source.add_rows(
        "kb1",
        "claim_record",
        [
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=1.0, observed_at=MONDAY),
            ColumnRow(entity_id="provider:2", entity_type="provider",
                      group_values=(), value=5.0, observed_at=MONDAY),
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=9.0, observed_at=tuesday_next),
            ColumnRow(entity_id="provider:2", entity_type="provider",
                      group_values=(), value=1.0, observed_at=tuesday_next),
        ],
    )
    response = _service(source, writer).compute(
        PeerStatsComputeRequest(
            knowledge_base_id="kb1", spec=_spec(),
            interval_starts=[MONDAY, week2_start], correlation_id="c1",
        )
    )
    # 2 entities x 2 intervals = 4 signals; affected ids deduped to 2.
    assert response.signals_written == 4
    assert response.affected_entity_ids == ["provider:1", "provider:2"]


class _RaisingColumnSource:
    """A column source that always fails, to test error propagation."""

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        raise PeerStatsSourceError("boom")


def test_source_error_propagates() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    service = create_peerstats_service(_RaisingColumnSource(), writer=writer)
    with pytest.raises(PeerStatsSourceError, match="boom"):
        service.compute(
            PeerStatsComputeRequest(
                knowledge_base_id="kb1", spec=_spec(),
                interval_starts=[MONDAY], correlation_id="c1",
            )
        )
