"""Tests for monitoring module models."""

from __future__ import annotations

import pytest

from monitoring.models import MonitoringBatch, MonitoringObservation
from monitoring.service_models import MonitoringEvaluationRequest


def test_monitoring_batch_requires_observations() -> None:
    with pytest.raises(ValueError, match="at least one observation"):
        MonitoringBatch(knowledge_base_id="kb-1", batch_id="batch-1", observations=[])


def test_monitoring_request_requires_ordered_thresholds() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        MonitoringEvaluationRequest(
            knowledge_base_id="kb-1",
            batch_id="batch-1",
            medium_threshold=0.8,
            high_threshold=0.7,
        )