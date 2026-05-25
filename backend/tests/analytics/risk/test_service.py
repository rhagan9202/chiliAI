"""Tests for the risk service."""

from __future__ import annotations

import math

import pytest

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.adapters.linear_strategy import LinearScoringStrategy
from analytics.risk.adapters.protocols import RiskSignalSourceProtocol
from analytics.risk.exceptions import (
    RiskConfigurationError,
    RiskInsufficientSignalsError,
    RiskSourceError,
)
from analytics.risk.models import RankedRiskEntry, RiskFactor, RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskAssessmentRequest, RiskScoreListRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import RiskScoredEvent


def test_risk_service_scores_profile_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="provider-7",
                    signals=[
                        RiskSignal(signal_name="timeseries", value=0.9, weight=2.0, rationale="spike"),
                        RiskSignal(signal_name="gnn_cluster", value=0.8, weight=1.5, rationale="dense cluster"),
                        RiskSignal(signal_name="billing_pattern", value=0.6, weight=1.0, rationale="outlier"),
                    ],
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.assess(RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7"))

    assert response.risk_level == "high"
    assert response.factor_count == 3
    assert response.overall_score == 0.8
    assert isinstance(event_bus.published_events[-1], RiskScoredEvent)


def test_risk_service_requires_multiple_signals() -> None:
    event_bus = InMemoryEventBus()
    service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="provider-7",
                    signals=[RiskSignal(signal_name="timeseries", value=0.9, weight=2.0)],
                )
            ]
        ),
        event_bus=event_bus,
    )

    with pytest.raises(RiskInsufficientSignalsError, match="at least two signals"):
        service.assess(RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7"))


def test_risk_service_list_scores_filters_and_orders() -> None:
    source = InMemoryRiskSignalSource(
        ranked_entries=[
            RankedRiskEntry(
                knowledge_base_id="kb-1",
                entity_id="provider-1",
                entity_type="provider",
                overall_score=0.5,
                risk_level="medium",
            ),
            RankedRiskEntry(
                knowledge_base_id="kb-1",
                entity_id="provider-2",
                entity_type="provider",
                overall_score=0.95,
                risk_level="high",
            ),
            RankedRiskEntry(
                knowledge_base_id="kb-1",
                entity_id="claim-3",
                entity_type="claim",
                overall_score=0.4,
                risk_level="low",
            ),
            RankedRiskEntry(
                knowledge_base_id="kb-2",
                entity_id="provider-9",
                entity_type="provider",
                overall_score=0.99,
                risk_level="high",
            ),
        ]
    )
    service = create_risk_service(source, event_bus=InMemoryEventBus())

    response = service.list_scores(
        RiskScoreListRequest(knowledge_base_id="kb-1", entity_type="provider", limit=5)
    )

    assert response.total == 2
    assert [item.entity_id for item in response.items] == ["provider-2", "provider-1"]


class _ValueErrorSource:
    def load_profile(self, *, knowledge_base_id: str, entity_id: str) -> RiskProfile:
        raise NotImplementedError

    def list_ranked_entries(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str | None,
        limit: int,
    ) -> list[RankedRiskEntry]:
        del knowledge_base_id, entity_type, limit
        raise ValueError("bad request")

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        del knowledge_base_id, entity_id
        return None


class _RuntimeErrorSource:
    def load_profile(self, *, knowledge_base_id: str, entity_id: str) -> RiskProfile:
        raise NotImplementedError

    def list_ranked_entries(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str | None,
        limit: int,
    ) -> list[RankedRiskEntry]:
        del knowledge_base_id, entity_type, limit
        raise RuntimeError("source down")

    def load_historical_score(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> float | None:
        del knowledge_base_id, entity_id
        return None


def test_risk_service_list_scores_translates_value_error() -> None:
    source: RiskSignalSourceProtocol = _ValueErrorSource()
    service = create_risk_service(source, event_bus=InMemoryEventBus())

    with pytest.raises(RiskConfigurationError, match="bad request"):
        service.list_scores(RiskScoreListRequest(knowledge_base_id="kb-1"))


def test_risk_service_list_scores_translates_runtime_error() -> None:
    source: RiskSignalSourceProtocol = _RuntimeErrorSource()
    service = create_risk_service(source, event_bus=InMemoryEventBus())

    with pytest.raises(RiskSourceError, match="ranked risk scores"):
        service.list_scores(RiskScoreListRequest(knowledge_base_id="kb-1"))


class _RecordingStrategy:
    def __init__(self, factors: list[RiskFactor]) -> None:
        self._factors = factors
        self.calls: list[list[RiskSignal]] = []

    def score(self, signals: list[RiskSignal]) -> list[RiskFactor]:
        self.calls.append(list(signals))
        return list(self._factors)


def _build_profile() -> RiskProfile:
    return RiskProfile(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        signals=[
            RiskSignal(signal_name="timeseries", value=0.9, weight=2.0, rationale="spike"),
            RiskSignal(signal_name="gnn_cluster", value=0.8, weight=1.5, rationale="dense cluster"),
            RiskSignal(signal_name="billing_pattern", value=0.6, weight=1.0, rationale="outlier"),
        ],
    )


def test_linear_strategy_matches_legacy_inline_implementation() -> None:
    profile = _build_profile()
    strategy = LinearScoringStrategy()

    factors = strategy.score(profile.signals)
    overall = sum(factor.contribution for factor in factors)

    assert len(factors) == 3
    assert factors[0].factor_name == "timeseries"
    assert math.isclose(factors[0].contribution, 0.4)
    assert math.isclose(factors[1].contribution, 0.8 * 1.5 / 4.5)
    assert math.isclose(factors[2].contribution, 0.6 * 1.0 / 4.5)
    assert math.isclose(overall, 0.8)


def test_linear_strategy_normalizes_contributions_by_total_weight() -> None:
    signals = [
        RiskSignal(signal_name="dominant", value=1.0, weight=10.0),
        RiskSignal(signal_name="other", value=0.1, weight=0.1),
    ]
    factors = LinearScoringStrategy().score(signals)

    total_weight = 10.1
    assert math.isclose(factors[0].contribution, (1.0 * 10.0) / total_weight)
    assert math.isclose(factors[1].contribution, (0.1 * 0.1) / total_weight)
    assert all(0.0 <= f.contribution <= 1.0 for f in factors)


def test_risk_service_delegates_to_injected_scoring_strategy() -> None:
    strategy = _RecordingStrategy(
        factors=[
            RiskFactor(
                factor_name="custom",
                raw_value=0.5,
                weight=1.0,
                contribution=0.3,
                rationale="injected",
            ),
            RiskFactor(
                factor_name="custom_2",
                raw_value=0.4,
                weight=1.0,
                contribution=0.2,
                rationale=None,
            ),
        ]
    )
    service = create_risk_service(
        InMemoryRiskSignalSource(profiles=[_build_profile()]),
        event_bus=InMemoryEventBus(),
        scoring_strategy=strategy,
    )

    response = service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    )

    assert len(strategy.calls) == 1
    assert [signal.signal_name for signal in strategy.calls[0]] == [
        "timeseries",
        "gnn_cluster",
        "billing_pattern",
    ]
    assert response.factor_count == 2
    assert [factor.factor_name for factor in response.factors] == ["custom", "custom_2"]
    assert math.isclose(response.overall_score, 0.5)


def test_risk_service_default_strategy_preserves_backward_compat() -> None:
    service_with_default = create_risk_service(
        InMemoryRiskSignalSource(profiles=[_build_profile()]),
        event_bus=InMemoryEventBus(),
    )
    service_with_explicit = create_risk_service(
        InMemoryRiskSignalSource(profiles=[_build_profile()]),
        event_bus=InMemoryEventBus(),
        scoring_strategy=LinearScoringStrategy(),
    )

    request = RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    default_response = service_with_default.assess(request)
    explicit_response = service_with_explicit.assess(request)

    assert default_response.overall_score == explicit_response.overall_score
    assert [factor.factor_name for factor in default_response.factors] == [
        factor.factor_name for factor in explicit_response.factors
    ]
    assert default_response.trend is None
    assert default_response.previous_score is None


def test_risk_service_trend_is_none_without_history() -> None:
    service = create_risk_service(
        InMemoryRiskSignalSource(profiles=[_build_profile()]),
        event_bus=InMemoryEventBus(),
    )

    response = service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    )

    assert response.trend is None
    assert response.previous_score is None


def test_risk_service_trend_increasing() -> None:
    source = InMemoryRiskSignalSource(
        profiles=[_build_profile()],
        historical_scores={("kb-1", "provider-7"): 0.6},
    )
    service = create_risk_service(source, event_bus=InMemoryEventBus())

    response = service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    )

    assert response.previous_score == 0.6
    assert response.trend == "increasing"


def test_risk_service_trend_decreasing() -> None:
    source = InMemoryRiskSignalSource(
        profiles=[_build_profile()],
        historical_scores={("kb-1", "provider-7"): 0.95},
    )
    service = create_risk_service(source, event_bus=InMemoryEventBus())

    response = service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    )

    assert response.previous_score == 0.95
    assert response.trend == "decreasing"


def test_risk_service_trend_stable_within_threshold() -> None:
    source = InMemoryRiskSignalSource(
        profiles=[_build_profile()],
        historical_scores={("kb-1", "provider-7"): 0.78},
    )
    service = create_risk_service(source, event_bus=InMemoryEventBus())

    response = service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    )

    assert response.previous_score == 0.78
    assert response.trend == "stable"


def test_risk_service_trend_respects_custom_delta_threshold() -> None:
    source = InMemoryRiskSignalSource(
        profiles=[_build_profile()],
        historical_scores={("kb-1", "provider-7"): 0.7},
    )
    service = create_risk_service(
        source,
        event_bus=InMemoryEventBus(),
        delta_threshold=0.2,
    )

    response = service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="provider-7")
    )

    assert response.previous_score == 0.7
    assert response.trend == "stable"


def test_assess_publishes_factors_on_risk_scored_event() -> None:
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.models import RiskProfile, RiskSignal
    from analytics.risk.service import create_risk_service
    from analytics.risk.service_models import RiskAssessmentRequest
    from events.adapters.in_memory import InMemoryEventBus
    from events.types import RiskScoredEvent

    profile = RiskProfile(
        knowledge_base_id="kb-1",
        entity_id="claim:c1",
        signals=[
            RiskSignal(signal_name="anomaly", value=0.9, weight=1.0),
            RiskSignal(signal_name="volume", value=0.4, weight=1.0),
        ],
    )
    event_bus = InMemoryEventBus()
    service = create_risk_service(
        InMemoryRiskSignalSource(profiles=[profile]), event_bus=event_bus
    )
    service.assess(
        RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="claim:c1")
    )
    published = [e for e in event_bus.published_events if isinstance(e, RiskScoredEvent)]
    assert len(published) == 1
    assert len(published[0].assessments[0].factors) == 2


def test_in_memory_source_returns_none_when_no_history_seeded() -> None:
    source = InMemoryRiskSignalSource()

    assert (
        source.load_historical_score(knowledge_base_id="kb-1", entity_id="provider-7")
        is None
    )


def test_in_memory_source_put_historical_score_updates_lookup() -> None:
    source = InMemoryRiskSignalSource()
    source.put_historical_score(
        knowledge_base_id="kb-1", entity_id="provider-7", score=0.42
    )

    assert (
        source.load_historical_score(knowledge_base_id="kb-1", entity_id="provider-7")
        == 0.42
    )