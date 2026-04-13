"""Tests for the in-memory monitoring adapter."""

from __future__ import annotations

from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.models import MonitoringBatch, MonitoringObservation


def test_in_memory_observation_source_returns_seeded_batch() -> None:
    batch = MonitoringBatch(
        knowledge_base_id="kb-1",
        batch_id="batch-1",
        observations=[
            MonitoringObservation(
                entity_id="provider-7",
                entity_type="provider",
                metric_name="claim_volume",
                score=0.92,
                rationale="Claim volume exceeded expected threshold.",
            )
        ],
    )
    source = InMemoryObservationSource(batches=[batch])

    loaded = source.load_batch(knowledge_base_id="kb-1", batch_id="batch-1")

    assert loaded == batch