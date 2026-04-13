"""Tests for the monitoring service."""

from __future__ import annotations

from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.models import MonitoringBatch, MonitoringObservation
from monitoring.service import create_monitoring_service
from monitoring.service_models import MonitoringEvaluationRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import AlertsCreatedEvent


def test_monitoring_service_generates_alerts_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_monitoring_service(
        InMemoryObservationSource(
            batches=[
                MonitoringBatch(
                    knowledge_base_id="kb-1",
                    batch_id="batch-1",
                    observations=[
                        MonitoringObservation(
                            entity_id="provider-7",
                            entity_type="provider",
                            metric_name="claim_volume",
                            score=0.92,
                            rationale="Claim volume exceeded expected threshold.",
                            evidence_pack_id="pack-1",
                        ),
                        MonitoringObservation(
                            entity_id="provider-8",
                            entity_type="provider",
                            metric_name="claim_volume",
                            score=0.55,
                            rationale="Below alert threshold.",
                        ),
                    ],
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.evaluate(MonitoringEvaluationRequest(knowledge_base_id="kb-1", batch_id="batch-1"))

    assert response.processed_observation_count == 2
    assert response.alert_count == 1
    assert response.alerts[0].entity_id == "provider-7"
    assert response.alerts[0].severity == "high"
    assert isinstance(event_bus.published_events[-1], AlertsCreatedEvent)


def test_monitoring_service_returns_no_alerts_below_threshold() -> None:
    event_bus = InMemoryEventBus()
    service = create_monitoring_service(
        InMemoryObservationSource(
            batches=[
                MonitoringBatch(
                    knowledge_base_id="kb-1",
                    batch_id="batch-1",
                    observations=[
                        MonitoringObservation(
                            entity_id="provider-8",
                            entity_type="provider",
                            metric_name="claim_volume",
                            score=0.55,
                            rationale="Below alert threshold.",
                        )
                    ],
                )
            ]
        ),
        event_bus=event_bus,
    )

    response = service.evaluate(MonitoringEvaluationRequest(knowledge_base_id="kb-1", batch_id="batch-1"))

    assert response.alert_count == 0
    assert response.alerts == []
    assert event_bus.published_events == []