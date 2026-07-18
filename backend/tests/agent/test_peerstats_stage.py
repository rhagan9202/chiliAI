"""Test the peerstats worker stage helpers with in-memory adapters."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.models import PeerAggregate
from analytics.peerstats.service import create_peerstats_service
from analytics.risk.exceptions import (
    RiskInsufficientSignalsError,
    RiskSourceError,
)
from analytics.risk.service_models import RiskAssessmentRequest, RiskAssessmentResponse
from analytics.timeseries.adapters.in_memory import InMemoryTimeseriesAnomalyStore
from agent.coordinator import assess_entities, run_peerstats_stage, run_timeseries_stage
from config.schema import (
    PeerMetricSpec,
    PeerStatsConfig,
    TimeseriesAnalyticsConfig,
    TimeseriesMetricSpec,
)
from events.adapters.in_memory import InMemoryEventBus

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _spec(name: str) -> PeerMetricSpec:
    return PeerMetricSpec(
        name=name, record_type="claim_record", entity_type="provider",
        entity_id_field="provider_npi", value_column="billed_amount",
        aggregation="sum", interval="week", min_peers=2,
    )


class _FakeColumnSource:
    """Protocol double returning canned aggregates; records the spec used.

    Mirrors the double in ``tests/analytics/timeseries/test_record_aggregates.py``.
    """

    def __init__(self, aggregates: list[PeerAggregate]) -> None:
        self._aggregates = aggregates
        self.last_spec: PeerMetricSpec | None = None

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        self.last_spec = spec
        return self._aggregates


def _weekly_aggregates(entity_id: str, values: list[float]) -> list[PeerAggregate]:
    """One weekly bucket per value, starting at ``MONDAY``, in ascending order."""

    return [
        PeerAggregate(
            entity_id=entity_id,
            entity_type="provider",
            peer_group_key="provider",
            interval_start=MONDAY + timedelta(weeks=index),
            aggregate_value=value,
        )
        for index, value in enumerate(values)
    ]


def _stage_spec(*, baseline_window: int = 3, min_history: int = 5) -> TimeseriesMetricSpec:
    """Task 3's ``_spec()`` (test_record_aggregates.py) with stage-sized history."""

    return TimeseriesMetricSpec(
        name="weekly_billing_self",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="npi",
        value_column="amount",
        aggregation="sum",
        interval="week",
        time_column="service_date",
        baseline_window=baseline_window,
        min_history=min_history,
    )


def test_timeseries_stage_persists_anomalies_and_signals_and_returns_affected() -> None:
    """A spiking series yields an anomaly row, a prefixed derived signal, and the entity id."""

    column_source = _FakeColumnSource(  # same double as Task 3's tests; 7 weekly buckets,
        _weekly_aggregates("provider:1", [100.0, 110.0, 90.0, 105.0, 95.0, 100.0, 900.0])
    )
    anomaly_store = InMemoryTimeseriesAnomalyStore()
    signal_writer = InMemoryDerivedRiskSignalWriter()
    affected = run_timeseries_stage(
        column_source=column_source,
        anomaly_store=anomaly_store,
        signal_writer=signal_writer,
        event_bus=InMemoryEventBus(),
        timeseries_config=TimeseriesAnalyticsConfig(metrics=[_stage_spec()]),
        knowledge_base_id="kb-1",
        record_type="claim_record",
        correlation_id="corr-1",
    )
    assert affected == ["provider:1"]
    stored = anomaly_store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name=_stage_spec().name
    )
    assert stored and stored[-1].observed_value == 900.0
    written = signal_writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:1")
    assert written[-1].metric_name == f"timeseries_anomaly:{_stage_spec().name}"
    assert 0.0 <= written[-1].signal_value <= 1.0


def test_timeseries_stage_skips_specs_for_other_record_types() -> None:
    """record_type mismatch -> no queries, no writes, empty affected."""

    column_source = _FakeColumnSource(
        _weekly_aggregates("provider:1", [100.0, 110.0, 90.0, 105.0, 95.0, 100.0, 900.0])
    )
    anomaly_store = InMemoryTimeseriesAnomalyStore()
    signal_writer = InMemoryDerivedRiskSignalWriter()
    affected = run_timeseries_stage(
        column_source=column_source,
        anomaly_store=anomaly_store,
        signal_writer=signal_writer,
        event_bus=InMemoryEventBus(),
        timeseries_config=TimeseriesAnalyticsConfig(metrics=[_stage_spec()]),
        knowledge_base_id="kb-1",
        record_type="other_record",
        correlation_id="corr-1",
    )
    assert affected == []
    assert column_source.last_spec is None
    assert anomaly_store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name=_stage_spec().name
    ) == []
    assert signal_writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:1") == []


def test_timeseries_stage_short_history_is_a_controlled_skip() -> None:
    """3 buckets with min_history=6 -> no anomalies, no signals, no exception."""

    column_source = _FakeColumnSource(
        _weekly_aggregates("provider:1", [100.0, 110.0, 90.0])
    )
    anomaly_store = InMemoryTimeseriesAnomalyStore()
    signal_writer = InMemoryDerivedRiskSignalWriter()
    affected = run_timeseries_stage(
        column_source=column_source,
        anomaly_store=anomaly_store,
        signal_writer=signal_writer,
        event_bus=InMemoryEventBus(),
        timeseries_config=TimeseriesAnalyticsConfig(
            metrics=[_stage_spec(min_history=6)]
        ),
        knowledge_base_id="kb-1",
        record_type="claim_record",
        correlation_id="corr-1",
    )
    assert affected == []
    assert anomaly_store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name=_stage_spec().name
    ) == []
    assert signal_writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:1") == []


def test_timeseries_stage_clamps_infinite_z_scores() -> None:
    """Flat baseline then a jump produces z=inf; stored z_score and severity are finite."""

    column_source = _FakeColumnSource(
        _weekly_aggregates("provider:1", [100.0, 100.0, 100.0, 100.0, 500.0])
    )
    anomaly_store = InMemoryTimeseriesAnomalyStore()
    signal_writer = InMemoryDerivedRiskSignalWriter()
    affected = run_timeseries_stage(
        column_source=column_source,
        anomaly_store=anomaly_store,
        signal_writer=signal_writer,
        event_bus=InMemoryEventBus(),
        timeseries_config=TimeseriesAnalyticsConfig(metrics=[_stage_spec()]),
        knowledge_base_id="kb-1",
        record_type="claim_record",
        correlation_id="corr-1",
    )
    assert affected == ["provider:1"]
    stored = anomaly_store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name=_stage_spec().name
    )
    assert stored and math.isfinite(stored[-1].z_score)
    assert stored[-1].severity == 1.0  # clamped z far exceeds z_cap -> signal saturates
    written = signal_writer.latest_signals(knowledge_base_id="kb-1", entity_id="provider:1")
    assert written and math.isfinite(written[-1].z_score)
    assert math.isfinite(written[-1].signal_value)


def test_run_peerstats_stage_returns_deduped_affected_entities() -> None:
    source = InMemoryRecordColumnSource()
    source.add_rows("kb1", "claim_record", [
        ColumnRow(entity_id="provider:1", entity_type="provider",
                  group_values=(), value=10.0, observed_at=MONDAY),
        ColumnRow(entity_id="provider:2", entity_type="provider",
                  group_values=(), value=2.0, observed_at=MONDAY),
    ])
    writer = InMemoryDerivedRiskSignalWriter()
    service = create_peerstats_service(source, writer=writer)
    config = PeerStatsConfig(metrics=[_spec("m1"), _spec("m2")])

    affected = run_peerstats_stage(
        peerstats_service=service,
        peer_stats_config=config,
        knowledge_base_id="kb1",
        record_type="claim_record",
        correlation_id="c1",
    )
    # provider:1 and provider:2 each touched by two specs → deduped to two ids.
    assert affected == ["provider:1", "provider:2"]


def test_run_peerstats_stage_skips_nonmatching_record_type() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    service = create_peerstats_service(source, writer=writer)
    config = PeerStatsConfig(metrics=[_spec("m1")])
    affected = run_peerstats_stage(
        peerstats_service=service,
        peer_stats_config=config,
        knowledge_base_id="kb1",
        record_type="other_record",
        correlation_id="c1",
    )
    assert affected == []


class _RecordingRiskService:
    """A risk service stub: records assess calls; fails for one entity."""

    def __init__(self) -> None:
        self.assessed: list[str] = []
        self.request_ids: list[str | None] = []

    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
        self.assessed.append(request.entity_id)
        self.request_ids.append(request.request_id)
        if request.entity_id == "provider:bad":
            raise RiskInsufficientSignalsError("no signals")
        return RiskAssessmentResponse(
            request_id="r",
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
            overall_score=0.5,
            risk_level="medium",
            factor_count=0,
        )


def test_assess_entities_counts_successes_and_skips_risk_error() -> None:
    risk = _RecordingRiskService()
    count = assess_entities(
        risk_service=risk,  # type: ignore[arg-type]
        knowledge_base_id="kb1",
        entity_ids=["provider:good", "provider:bad"],
        correlation_id="corr-1",
    )
    assert count == 1
    assert risk.assessed == ["provider:good", "provider:bad"]
    # Deterministic, correlation-scoped request id → idempotent on retry.
    assert risk.request_ids == [
        "risk:corr-1:kb1:provider:good",
        "risk:corr-1:kb1:provider:bad",
    ]


class _FailingRiskService:
    """A risk service stub that raises an infrastructure error."""

    def assess(self, request: RiskAssessmentRequest) -> RiskAssessmentResponse:
        raise RiskSourceError("db down")


def test_assess_entities_propagates_infrastructure_errors() -> None:
    # RiskSourceError/RiskHistoryError are NOT swallowed — a DB outage must
    # surface (to the caller's exception logger) rather than look like a no-op.
    with pytest.raises(RiskSourceError):
        assess_entities(
            risk_service=_FailingRiskService(),  # type: ignore[arg-type]
            knowledge_base_id="kb1",
            entity_ids=["provider:1"],
            correlation_id="corr-1",
        )
