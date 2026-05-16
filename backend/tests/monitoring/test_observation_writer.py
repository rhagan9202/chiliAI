"""Tests for the in-memory observation writer."""

from __future__ import annotations

from monitoring.adapters.in_memory import InMemoryObservationWriter
from monitoring.adapters.protocols import ObservationWriter
from monitoring.models import MonitoringBatch, MonitoringObservation


def _batch() -> MonitoringBatch:
    return MonitoringBatch(
        knowledge_base_id="kb-1",
        batch_id="corr-1",
        observations=[
            MonitoringObservation(
                entity_id="claim:c1",
                entity_type="claim",
                metric_name="claim_anomaly",
                score=0.8,
                rationale="test",
            )
        ],
    )


def test_in_memory_writer_satisfies_protocol() -> None:
    writer: ObservationWriter = InMemoryObservationWriter()
    assert writer.write_observations(_batch(), correlation_id="corr-1") == 1


def test_in_memory_writer_records_written_batches() -> None:
    writer = InMemoryObservationWriter()
    writer.write_observations(_batch(), correlation_id="corr-1")
    assert len(writer.written) == 1
    batch, correlation_id = writer.written[0]
    assert batch.batch_id == "corr-1"
    assert correlation_id == "corr-1"
