"""Tests for risk module models."""

from __future__ import annotations

import pytest

from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service_models import RiskAssessmentRequest


def test_risk_profile_requires_unique_signal_names() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        RiskProfile(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            signals=[
                RiskSignal(signal_name="timeseries", value=0.7, weight=1.0),
                RiskSignal(signal_name="timeseries", value=0.8, weight=1.5),
            ],
        )


def test_risk_assessment_request_requires_ordered_thresholds() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        RiskAssessmentRequest(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            medium_risk_threshold=0.8,
            high_risk_threshold=0.7,
        )