"""API-owned alert projection stores and contract projection helpers.

The monitoring module owns alert generation and lifecycle semantics. The API
gateway owns this lightweight read projection so frontend routes can list,
inspect, and acknowledge alerts without depending on the legacy seeded
``ApiState`` object. Durable deployments can swap in a stronger metadata store
behind ``AlertProjectionRepository`` later without changing router contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from api.contracts import (
    AlertDetailResponse,
    AlertListItem,
    AlertListResponse,
    PageInfo,
    PolicyCitation,
)
from shared.alerts import normalize_severity
from shared.types import Alert
from shared.utils import utc_now
from storage.protocols import ObjectStore

__all__ = [
    "ACTIVE_ALERT_STATUSES",
    "AlertProjectionRecord",
    "AlertProjectionRepository",
    "InMemoryAlertProjectionRepository",
    "ObjectStoreAlertProjectionRepository",
    "acknowledge_alert_projection",
    "count_active_alerts",
    "project_alert_detail",
    "project_alert_feed",
]

ACTIVE_ALERT_STATUSES = {"open", "acknowledged", "investigating"}


class AlertProjectionRecord(BaseModel):
    """Stored read-model record for one analyst-facing alert."""

    alert: Alert
    entity_label: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    related_entity_ids: list[str] = Field(default_factory=list)
    policy_citations: list[PolicyCitation] = Field(
        default_factory=lambda: list[PolicyCitation]()
    )
    updated_at: datetime = Field(default_factory=utc_now)


class _AlertProjectionSnapshot(BaseModel):
    """Serialized repository state for object-store persistence."""

    alerts: dict[str, AlertProjectionRecord] = Field(default_factory=dict)
    alert_order: list[str] = Field(default_factory=list)


@runtime_checkable
class AlertProjectionRepository(Protocol):
    """Persistence boundary for API alert read projections."""

    def upsert(self, record: AlertProjectionRecord) -> AlertProjectionRecord: ...

    def get(self, alert_id: str) -> AlertProjectionRecord | None: ...

    def list(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertProjectionRecord], int]: ...

    def acknowledge(self, alert_id: str) -> AlertProjectionRecord | None: ...

    def count_by_statuses(self, statuses: set[str]) -> int: ...


class InMemoryAlertProjectionRepository:
    """Process-local alert read projection repository."""

    def __init__(self) -> None:
        self._alerts: dict[str, AlertProjectionRecord] = {}
        self._alert_order: list[str] = []

    def upsert(self, record: AlertProjectionRecord) -> AlertProjectionRecord:
        alert_id = record.alert.id
        if alert_id not in self._alerts:
            self._alert_order.append(alert_id)
        self._alerts[alert_id] = record.model_copy(update={"updated_at": utc_now()})
        return self._alerts[alert_id]

    def get(self, alert_id: str) -> AlertProjectionRecord | None:
        return self._alerts.get(alert_id)

    def list(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertProjectionRecord], int]:
        ordered_ids = self._sorted_alert_ids()
        page_ids = ordered_ids[offset : offset + limit]
        return [self._alerts[alert_id] for alert_id in page_ids], len(ordered_ids)

    def acknowledge(self, alert_id: str) -> AlertProjectionRecord | None:
        record = self._alerts.get(alert_id)
        if record is None:
            return None
        updated_alert = record.alert.model_copy(
            update={
                "status": "acknowledged",
                "acknowledged": True,
                "updated_at": utc_now(),
            }
        )
        updated = record.model_copy(
            update={"alert": updated_alert, "updated_at": utc_now()}
        )
        self._alerts[alert_id] = updated
        return updated

    def count_by_statuses(self, statuses: set[str]) -> int:
        return sum(
            1 for record in self._alerts.values() if record.alert.status in statuses
        )

    def _sorted_alert_ids(self) -> list[str]:
        return sorted(
            self._alert_order,
            key=lambda alert_id: self._alerts[alert_id].alert.created_at,
            reverse=True,
        )


class ObjectStoreAlertProjectionRepository:
    """Durable alert projection repository backed by the configured object store.

    This compact JSON snapshot is suitable for local/dev single-writer API
    deployments. Production installations that need high concurrency can
    implement the same protocol with a dedicated metadata database.
    """

    _DEFAULT_KEY = "system/alerts/projection.json"

    def __init__(
        self,
        object_store: ObjectStore,
        *,
        storage_key: str = _DEFAULT_KEY,
    ) -> None:
        self._object_store = object_store
        self._storage_key = storage_key

    def upsert(self, record: AlertProjectionRecord) -> AlertProjectionRecord:
        snapshot = self._load_snapshot()
        alert_id = record.alert.id
        if alert_id not in snapshot.alerts:
            snapshot.alert_order.append(alert_id)
        updated = record.model_copy(update={"updated_at": utc_now()})
        snapshot.alerts[alert_id] = updated
        self._save_snapshot(snapshot)
        return updated

    def get(self, alert_id: str) -> AlertProjectionRecord | None:
        return self._load_snapshot().alerts.get(alert_id)

    def list(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertProjectionRecord], int]:
        snapshot = self._load_snapshot()
        ordered_ids = self._sorted_alert_ids(snapshot)
        page_ids = ordered_ids[offset : offset + limit]
        return [snapshot.alerts[alert_id] for alert_id in page_ids], len(ordered_ids)

    def acknowledge(self, alert_id: str) -> AlertProjectionRecord | None:
        snapshot = self._load_snapshot()
        record = snapshot.alerts.get(alert_id)
        if record is None:
            return None
        updated_alert = record.alert.model_copy(
            update={
                "status": "acknowledged",
                "acknowledged": True,
                "updated_at": utc_now(),
            }
        )
        updated = record.model_copy(
            update={"alert": updated_alert, "updated_at": utc_now()}
        )
        snapshot.alerts[alert_id] = updated
        self._save_snapshot(snapshot)
        return updated

    def count_by_statuses(self, statuses: set[str]) -> int:
        snapshot = self._load_snapshot()
        return sum(
            1 for record in snapshot.alerts.values() if record.alert.status in statuses
        )

    def _load_snapshot(self) -> _AlertProjectionSnapshot:
        if not self._object_store.exists(self._storage_key):
            return _AlertProjectionSnapshot()
        stored = self._object_store.get_bytes(self._storage_key)
        return _AlertProjectionSnapshot.model_validate_json(stored.content)

    def _save_snapshot(self, snapshot: _AlertProjectionSnapshot) -> None:
        self._object_store.put_bytes(
            self._storage_key,
            snapshot.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={"record_type": "alert_projection"},
        )

    @staticmethod
    def _sorted_alert_ids(snapshot: _AlertProjectionSnapshot) -> list[str]:
        return sorted(
            snapshot.alert_order,
            key=lambda alert_id: snapshot.alerts[alert_id].alert.created_at,
            reverse=True,
        )


def project_alert_feed(
    repository: AlertProjectionRepository,
    *,
    limit: int = 100,
    offset: int = 0,
) -> AlertListResponse:
    """Return a paginated frontend alert feed from projection records."""

    records, total = repository.list(limit=limit, offset=offset)
    return AlertListResponse(
        items=[_to_alert_item(record) for record in records],
        page=PageInfo(page=1, page_size=max(limit, 1), total_items=total),
    )


def project_alert_detail(record: AlertProjectionRecord) -> AlertDetailResponse:
    """Return an alert detail contract from one projection record."""

    related_entity_ids = record.related_entity_ids or [record.alert.entity_id]
    return AlertDetailResponse(
        alert=_to_alert_item(record),
        related_entity_ids=list(related_entity_ids),
        policy_citations=list(record.policy_citations),
    )


def acknowledge_alert_projection(
    repository: AlertProjectionRepository,
    alert_id: str,
) -> AlertProjectionRecord | None:
    """Mark an alert projection acknowledged and return the updated record."""

    return repository.acknowledge(alert_id)


def count_active_alerts(repository: AlertProjectionRepository) -> int:
    """Return the number of active alerts for realtime workspace snapshots."""

    return repository.count_by_statuses(ACTIVE_ALERT_STATUSES)


def _to_alert_item(record: AlertProjectionRecord) -> AlertListItem:
    alert = record.alert
    return AlertListItem(
        id=alert.id,
        entity_id=alert.entity_id,
        entity_type=alert.entity_type,
        entity_label=record.entity_label or alert.entity_id,
        severity=normalize_severity(alert.severity, record.confidence),
        status=alert.status,
        title=alert.title,
        reasoning=alert.reasoning,
        confidence=record.confidence,
        evidence_pack_id=alert.evidence_pack_id,
        created_at=alert.created_at,
        tags=list(record.tags),
    )
