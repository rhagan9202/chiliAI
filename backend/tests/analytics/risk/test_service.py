"""Tests for the risk service."""

from __future__ import annotations

import pytest

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.exceptions import RiskInsufficientSignalsError
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from analytics.risk.service_models import RiskAssessmentRequest
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