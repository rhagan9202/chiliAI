"""Tests for timeseries module models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from analytics.timeseries.service_models import TimeseriesAnalysisRequest


def test_timeseries_series_requires_ordered_observations() -> None:
    with pytest.raises(ValueError, match="ordered by observed_at"):
        TimeSeriesSeries(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="claim_volume",
            observations=[
                TimeSeriesObservation(observed_at=datetime(2024, 1, 2, tzinfo=timezone.utc), value=12.0),
                TimeSeriesObservation(observed_at=datetime(2024, 1, 1, tzinfo=timezone.utc), value=10.0),
            ],
        )


def test_timeseries_analysis_request_requires_min_history_above_baseline() -> None:
    with pytest.raises(ValueError, match="min_history must exceed baseline_window"):
        TimeseriesAnalysisRequest(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="claim_volume",
            baseline_window=5,
            min_history=5,
        )