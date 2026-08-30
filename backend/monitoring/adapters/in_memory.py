"""In-memory observation source for tests and local development."""

from __future__ import annotations

import threading
from datetime import timedelta

from monitoring.exceptions import AlertConcurrentModificationError
from monitoring.lifecycle import validate_alert_transition
from monitoring.models import AlertHistoryRecord, MonitoringBatch
from monitoring.models import AlertTriageEvent
from monitoring.models import normalize_generation_metadata
from shared.types import Alert
from shared.utils import utc_now

__all__ = ["InMemoryAlertHistoryWriter", "InMemoryAlertRepository", "InMemoryObservationSource", "InMemoryObservationWriter"]


class InMemoryObservationSource:
    """A seeded source of monitoring batches keyed by knowledge base and batch id."""

    def __init__(self, batches: list[MonitoringBatch] | None = None) -> None:
        self._batches: dict[tuple[str, str], MonitoringBatch] = {}
        for batch in batches or []:
            self.put_batch(batch)

    def put_batch(self, batch: MonitoringBatch) -> None:
        self._batches[(batch.knowledge_base_id, batch.batch_id)] = batch

    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch:
        batch = self._batches.get((knowledge_base_id, batch_id))
        if batch is None:
            raise ValueError(
                f"No monitoring batch registered for knowledge_base_id='{knowledge_base_id}' and batch_id='{batch_id}'."
            )
        return batch


class InMemoryObservationWriter:
    """An ``ObservationWriter`` that records written batches in memory."""

    def __init__(self) -> None:
        self.written: list[tuple[MonitoringBatch, str]] = []

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        self.written.append((batch, correlation_id))
        return len(batch.observations)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        before = len(self.written)
        self.written = [
            (batch, corr_id)
            for batch, corr_id in self.written
            if batch.knowledge_base_id != knowledge_base_id
        ]
        return before - len(self.written)


class InMemoryAlertRepository:
    """A simple in-memory store of alerts keyed by alert id.

    Insertion order is preserved so list operations are deterministic.
    """

    def __init__(self, alerts: list[Alert] | None = None) -> None:
        self._alerts: dict[str, Alert] = {}
        for alert in alerts or []:
            self.put(alert)

    def put(self, alert: Alert) -> None:
        self._alerts[alert.id] = alert

    def get(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def all(self) -> list[Alert]:
        return list(self._alerts.values())


class InMemoryAlertHistoryWriter:
    """An ``AlertHistoryWriter`` that records alert rows in memory."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], AlertHistoryRecord] = {}
        # Postgres gets a compare-and-set for free from a `WHERE status = %s`
        # guarded UPDATE: a lost race there re-reads and either raises
        # AlertLifecycleError (the retried transition is no longer valid) or
        # AlertConcurrentModificationError (it is still valid, but something
        # else committed first -- reload and retry). acknowledge and
        # transition_status below reproduce the same two-step shape -- an
        # unguarded read of the status a caller is transitioning *from*,
        # then a lock-guarded re-check-and-write -- so two callers sharing
        # this process-wide singleton (get_alert_feed_store is
        # @lru_cache(maxsize=1), reused across every threadpool request) get
        # identical semantics to the Postgres adapter instead of a silent
        # lost write: without the lock, both can pass validation against the
        # same stale status and both write, the second silently discarding
        # the first's transition (and its own from_status audit claim going
        # stale with it).
        self._transition_lock = threading.Lock()

    def _find_by_alert_id(
        self, alert_id: str, knowledge_base_id: str | None
    ) -> tuple[tuple[str, str], AlertHistoryRecord] | None:
        for key, record in self._records.items():
            if record.alert_id == alert_id and (
                knowledge_base_id is None
                or record.knowledge_base_id == knowledge_base_id
            ):
                return key, record
        return None

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        written = 0
        for record in records:
            key = (record.knowledge_base_id, record.alert_id)
            if key in self._records:
                continue
            self._records[key] = record.model_copy(
                update={
                    "generation_metadata": normalize_generation_metadata(
                        record.generation_metadata
                    )
                }
            )
            written += 1
        return written

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        return sum(
            1
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
            and record.status == "open"
        )

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys_to_delete = [
            key for key in self._records if key[0] == knowledge_base_id
        ]
        for key in keys_to_delete:
            del self._records[key]
        return len(keys_to_delete)

    def list_alerts(
        self,
        *,
        knowledge_base_id: str | None = None,
        statuses: list[str] | None = None,
        severities: list[str] | None = None,
        tags: list[str] | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        evidence: str | None = None,
        freshness: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertHistoryRecord], int]:
        status_set = set(statuses) if statuses else None
        severity_set = set(severities) if severities else None
        tag_set = set(tags) if tags else None
        fresh_cutoff = utc_now() - timedelta(days=14)
        filtered = [
            record
            for record in self._records.values()
            if (status_set is None or record.status in status_set)
            and (severity_set is None or record.severity in severity_set)
            and (tag_set is None or bool(tag_set.intersection(record.tags)))
            and (
                created_from is None
                or record.created_at.date().isoformat() >= created_from
            )
            and (
                created_to is None
                or record.created_at.date().isoformat() <= created_to
            )
            and (
                evidence is None
                or (
                    evidence == "with_evidence"
                    and record.evidence_pack_id is not None
                )
                or (
                    evidence == "without_evidence"
                    and record.evidence_pack_id is None
                )
            )
            and (
                freshness is None
                or (freshness == "fresh" and record.updated_at >= fresh_cutoff)
                or (freshness == "stale" and record.updated_at < fresh_cutoff)
            )
            and (
                knowledge_base_id is None
                or record.knowledge_base_id == knowledge_base_id
            )
        ]
        ordered = sorted(
            filtered,
            key=lambda record: (record.created_at, record.alert_id),
            reverse=True,
        )
        total = len(ordered)
        return ordered[offset : offset + limit], total

    def get_alert(self, alert_id: str) -> AlertHistoryRecord | None:
        for record in self._records.values():
            if record.alert_id == alert_id:
                return record
        return None

    def acknowledge(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str | None = None,
        actor: str = "system",
    ) -> AlertHistoryRecord | None:
        found = self._find_by_alert_id(alert_id, knowledge_base_id)
        if found is None:
            return None
        key, observed = found
        validate_alert_transition(observed.status, "acknowledged")
        with self._transition_lock:
            current = self._records.get(key)
            if current is None:
                return None
            if current.status != observed.status:
                # Someone else's write landed between our unguarded read
                # above and this lock. Re-validate against the row as it
                # actually stands: still forbidden -> let AlertLifecycleError
                # propagate with the real from_status; still valid -> the
                # race, not the lifecycle, is the problem.
                validate_alert_transition(current.status, "acknowledged")
                raise AlertConcurrentModificationError(alert_id)
            now = utc_now()
            event = AlertTriageEvent(
                event_type="status_changed",
                actor=actor,
                occurred_at=now,
                from_status=current.status,
                to_status="acknowledged",
            )
            updated = current.model_copy(
                update={
                    "status": "acknowledged",
                    "updated_at": now,
                    "triage_history": [*current.triage_history, event],
                }
            )
            self._records[key] = updated
            return updated

    def assign(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        assignee: str | None,
        actor: str,
    ) -> AlertHistoryRecord | None:
        key = (knowledge_base_id, alert_id)
        record = self._records.get(key)
        if record is None:
            return None
        now = utc_now()
        event = AlertTriageEvent(
            event_type="assigned",
            actor=actor,
            occurred_at=now,
            assignee=assignee,
        )
        updated = record.model_copy(
            update={
                "assignee": assignee,
                "updated_at": now,
                "triage_history": [*record.triage_history, event],
            }
        )
        self._records[key] = updated
        return updated

    def transition_status(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        status: str,
        actor: str,
        reason: str | None = None,
    ) -> AlertHistoryRecord | None:
        key = (knowledge_base_id, alert_id)
        observed = self._records.get(key)
        if observed is None:
            return None
        validate_alert_transition(observed.status, status)
        with self._transition_lock:
            current = self._records.get(key)
            if current is None:
                return None
            if current.status != observed.status:
                # See acknowledge()'s identical guard above.
                validate_alert_transition(current.status, status)
                raise AlertConcurrentModificationError(alert_id)
            now = utc_now()
            event = AlertTriageEvent(
                event_type="status_changed",
                actor=actor,
                occurred_at=now,
                from_status=current.status,
                to_status=status,
                reason=reason,
            )
            updated = current.model_copy(
                update={
                    "status": status,
                    "updated_at": now,
                    "triage_history": [*current.triage_history, event],
                }
            )
            self._records[key] = updated
            return updated

    def count_by_statuses(self, statuses: set[str]) -> int:
        return sum(
            1 for record in self._records.values() if record.status in statuses
        )
