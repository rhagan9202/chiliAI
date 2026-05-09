"""Tests for the AlertsService and the in-memory alert repository."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from monitoring.adapters.in_memory import InMemoryAlertRepository
from monitoring.exceptions import AlertAlreadyResolvedError, AlertNotFoundError
from monitoring.service import AlertsService, create_alerts_service
from monitoring.service_models import AlertListRequest, ResolutionRequest
from shared.types import Alert


def _alert(
    *,
    alert_id: str,
    severity: str = "high",
    entity_type: str = "provider",
    status: str = "open",
) -> Alert:
    return Alert(
        id=alert_id,
        entity_type=entity_type,
        entity_id=f"{entity_type}-{alert_id}",
        severity=severity,
        title="Threshold exceeded",
        reasoning="Score exceeded threshold.",
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        status=status,  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture()
def service() -> AlertsService:
    repository = InMemoryAlertRepository(
        alerts=[
            _alert(alert_id="a-1", severity="high", entity_type="provider", status="open"),
            _alert(alert_id="a-2", severity="medium", entity_type="provider", status="open"),
            _alert(alert_id="a-3", severity="high", entity_type="claim", status="resolved"),
        ]
    )
    return create_alerts_service(repository)


class TestListAlerts:
    def test_returns_all_when_no_filter(self, service: AlertsService) -> None:
        response = service.list_alerts(AlertListRequest())

        assert response.total == 3
        assert [alert.id for alert in response.items] == ["a-1", "a-2", "a-3"]

    def test_filters_by_severity(self, service: AlertsService) -> None:
        response = service.list_alerts(AlertListRequest(severity="high"))

        assert response.total == 2
        assert {alert.id for alert in response.items} == {"a-1", "a-3"}

    def test_filters_by_entity_type(self, service: AlertsService) -> None:
        response = service.list_alerts(AlertListRequest(entity_type="claim"))

        assert response.total == 1
        assert response.items[0].id == "a-3"

    def test_filters_by_status(self, service: AlertsService) -> None:
        response = service.list_alerts(AlertListRequest(status="open"))

        assert response.total == 2
        assert {alert.id for alert in response.items} == {"a-1", "a-2"}

    def test_paginates_results(self, service: AlertsService) -> None:
        response = service.list_alerts(AlertListRequest(limit=1, offset=1))

        assert response.total == 3
        assert [alert.id for alert in response.items] == ["a-2"]


class TestAcknowledgeAlert:
    def test_acknowledge_open_alert(self, service: AlertsService) -> None:
        alert = service.acknowledge_alert("a-1")

        assert alert.status == "acknowledged"
        assert alert.acknowledged is True
        assert alert.updated_at is not None

    def test_acknowledge_unknown_alert_raises(self, service: AlertsService) -> None:
        with pytest.raises(AlertNotFoundError):
            service.acknowledge_alert("missing")

    def test_acknowledge_resolved_alert_raises(self, service: AlertsService) -> None:
        with pytest.raises(AlertAlreadyResolvedError):
            service.acknowledge_alert("a-3")


class TestResolveAlert:
    def test_resolve_open_alert(self, service: AlertsService) -> None:
        alert = service.resolve_alert(
            "a-1",
            ResolutionRequest(resolved_by="analyst@example.com", notes="Confirmed fraud."),
        )

        assert alert.status == "resolved"
        assert alert.resolved_by == "analyst@example.com"
        assert alert.resolution_notes == "Confirmed fraud."
        assert alert.updated_at is not None

    def test_resolve_acknowledged_alert(self, service: AlertsService) -> None:
        service.acknowledge_alert("a-1")

        resolved = service.resolve_alert(
            "a-1",
            ResolutionRequest(resolved_by="analyst@example.com"),
        )

        assert resolved.status == "resolved"
        assert resolved.resolution_notes is None

    def test_resolve_unknown_alert_raises(self, service: AlertsService) -> None:
        with pytest.raises(AlertNotFoundError):
            service.resolve_alert(
                "missing",
                ResolutionRequest(resolved_by="analyst@example.com"),
            )

    def test_resolve_already_resolved_alert_raises(
        self, service: AlertsService
    ) -> None:
        with pytest.raises(AlertAlreadyResolvedError):
            service.resolve_alert(
                "a-3",
                ResolutionRequest(resolved_by="analyst@example.com"),
            )


class TestRepository:
    def test_seeded_alerts_round_trip(self) -> None:
        seed = _alert(alert_id="a-1")
        repository = InMemoryAlertRepository(alerts=[seed])

        assert repository.get("a-1") == seed
        assert repository.get("missing") is None
        assert repository.all() == [seed]

    def test_put_overwrites_existing_alert(self) -> None:
        original = _alert(alert_id="a-1", status="open")
        repository = InMemoryAlertRepository(alerts=[original])
        updated = original.model_copy(update={"status": "acknowledged"})

        repository.put(updated)

        assert repository.get("a-1") == updated
        assert len(repository.all()) == 1
