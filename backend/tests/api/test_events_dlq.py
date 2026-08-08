"""Tests for the /events/dlq operator surface (BL-023)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_dlq_record_store, get_domain_config, get_event_bus
from api.middleware.auth import User, get_current_user
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.adapters.in_memory import InMemoryEventBus
from events.codec import encode_event
from events.dlq_models import DlqRecord, DlqRecordStatus
from events.protocols import DlqRecordStore
from events.types import KnowledgeBaseCreatedEvent
from shared.utils import utc_now

_BASE_TIME = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _domain_with_auth() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _make_record(
    dlq_id: str,
    *,
    status: DlqRecordStatus = "pending",
    event_type: str = "kb.create",
    payload: dict[str, str] | None = None,
    created_at: datetime | None = None,
) -> DlqRecord:
    return DlqRecord(
        dlq_id=dlq_id,
        event_type=event_type,
        correlation_id=f"corr-{dlq_id}",
        payload=payload or {"event_type": event_type, "event_body": "{}"},
        error_message="boom",
        error_traceback="Traceback (most recent call last):\n  ...\nRuntimeError: boom",
        retry_count=3,
        failed_at=created_at or utc_now(),
        status=status,
        created_at=created_at or utc_now(),
    )


def _build_app(
    *,
    store: DlqRecordStore,
    event_bus: InMemoryEventBus | None = None,
    auth_enabled: bool = False,
    roles: list[str] | None = None,
) -> FastAPI:
    app = create_app()
    if auth_enabled:
        app.dependency_overrides[get_domain_config] = _domain_with_auth
    if roles is not None:
        app.dependency_overrides[get_current_user] = lambda: User(
            user_id="operator", roles=roles
        )
    app.dependency_overrides[get_dlq_record_store] = lambda: store
    if event_bus is not None:
        app.dependency_overrides[get_event_bus] = lambda: event_bus
    return app


def test_list_dlq_returns_paginated_records() -> None:
    store = InMemoryDlqRecordStore()
    older = _make_record("dlq-older", created_at=_BASE_TIME)
    newer = _make_record("dlq-newer", created_at=_BASE_TIME + timedelta(minutes=5))
    store.persist(older)
    store.persist(newer)
    app = _build_app(store=store)

    with TestClient(app) as client:
        response = client.get("/events/dlq")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["dlq_id"] for item in body["items"]] == ["dlq-newer", "dlq-older"]
    assert body["items"][0]["status"] == "pending"
    # Full DlqRecord shape (traceback included) — no separate summary shape.
    assert "error_traceback" in body["items"][0]
    assert body["items"][0]["error_traceback"] == newer.error_traceback
    assert body["items"][1]["error_traceback"] == older.error_traceback


def test_list_dlq_filters_by_status_and_event_type() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_make_record("dlq-pending", status="pending", event_type="kb.create"))
    store.persist(_make_record("dlq-replayed", status="replayed", event_type="kb.delete"))
    app = _build_app(store=store)

    with TestClient(app) as client:
        by_status = client.get("/events/dlq", params={"status": "replayed"})
        by_event_type = client.get("/events/dlq", params={"event_type": "kb.create"})

    assert by_status.status_code == 200
    assert [item["dlq_id"] for item in by_status.json()["items"]] == ["dlq-replayed"]
    assert by_event_type.status_code == 200
    assert [item["dlq_id"] for item in by_event_type.json()["items"]] == ["dlq-pending"]


def test_get_dlq_record_and_404() -> None:
    store = InMemoryDlqRecordStore()
    record = _make_record("dlq-1")
    store.persist(record)
    app = _build_app(store=store)

    with TestClient(app) as client:
        found = client.get("/events/dlq/dlq-1")
        missing = client.get("/events/dlq/unknown")

    assert found.status_code == 200
    assert found.json()["dlq_id"] == "dlq-1"
    assert found.json()["error_traceback"] == record.error_traceback
    assert missing.status_code == 404


def test_replay_publishes_and_marks_replayed() -> None:
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-99")
    payload = encode_event(event)
    store = InMemoryDlqRecordStore()
    store.persist(_make_record("dlq-1", event_type=event.event_type, payload=payload))
    bus = InMemoryEventBus()
    app = _build_app(store=store, event_bus=bus)

    with TestClient(app) as client:
        first = client.post("/events/dlq/dlq-1/replay")
        second = client.post("/events/dlq/dlq-1/replay")

    assert first.status_code == 200
    assert first.json()["status"] == "replayed"
    assert len(bus.published_events) == 1
    replayed_event = bus.published_events[0]
    assert isinstance(replayed_event, KnowledgeBaseCreatedEvent)
    assert replayed_event.knowledge_base_id == "kb-99"

    assert second.status_code == 409


def test_replay_unknown_id_is_404() -> None:
    store = InMemoryDlqRecordStore()
    bus = InMemoryEventBus()
    app = _build_app(store=store, event_bus=bus)

    with TestClient(app) as client:
        response = client.post("/events/dlq/does-not-exist/replay")

    assert response.status_code == 404
    assert bus.published_events == []


def test_replay_undecodable_payload_is_422_and_stays_pending() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(
        _make_record(
            "dlq-1",
            event_type="nope.unknown",
            payload={"event_type": "nope.unknown", "event_body": "{}"},
        )
    )
    bus = InMemoryEventBus()
    app = _build_app(store=store, event_bus=bus)

    with TestClient(app) as client:
        replay_response = client.post("/events/dlq/dlq-1/replay")
        get_response = client.get("/events/dlq/dlq-1")

    assert replay_response.status_code == 422
    assert bus.published_events == []
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "pending"


def test_discard_marks_discarded_and_409_on_repeat() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_make_record("dlq-1"))
    app = _build_app(store=store)

    with TestClient(app) as client:
        first = client.post("/events/dlq/dlq-1/discard")
        second = client.post("/events/dlq/dlq-1/discard")
        missing = client.post("/events/dlq/unknown/discard")

    assert first.status_code == 200
    assert first.json()["status"] == "discarded"
    assert second.status_code == 409
    assert missing.status_code == 404


class _RaceOnReplayStore(InMemoryDlqRecordStore):
    """Simulates another operator winning the CAS between ``get`` and
    ``mark_replayed`` — used to exercise the replay route's concurrent-
    transition 409 branch, which the single-threaded in-memory store can't
    otherwise reach.
    """

    def mark_replayed(self, dlq_id: str) -> DlqRecord | None:
        return None


def test_replay_returns_409_when_transitioned_concurrently() -> None:
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-race")
    payload = encode_event(event)
    store = _RaceOnReplayStore()
    store.persist(_make_record("dlq-1", event_type=event.event_type, payload=payload))
    bus = InMemoryEventBus()
    app = _build_app(store=store, event_bus=bus)

    with TestClient(app) as client:
        response = client.post("/events/dlq/dlq-1/replay")

    assert response.status_code == 409
    # The event was still published before the race was detected.
    assert len(bus.published_events) == 1


def test_list_dlq_pagination_window() -> None:
    """Verify pagination window returns correct slice with newest-first ordering."""
    store = InMemoryDlqRecordStore()
    r1 = _make_record("dlq-oldest", created_at=_BASE_TIME)
    r2 = _make_record("dlq-middle", created_at=_BASE_TIME + timedelta(minutes=5))
    r3 = _make_record("dlq-newest", created_at=_BASE_TIME + timedelta(minutes=10))
    store.persist(r1)
    store.persist(r2)
    store.persist(r3)
    app = _build_app(store=store)

    with TestClient(app) as client:
        response = client.get("/events/dlq", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # Newest-first: [dlq-newest, dlq-middle, dlq-oldest]
    # offset=1, limit=2 should return: [dlq-middle, dlq-oldest]
    assert [item["dlq_id"] for item in body["items"]] == ["dlq-middle", "dlq-oldest"]


def test_role_gates() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_make_record("dlq-1"))
    # Add a second record with a properly encoded event for testing replay-200.
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-replay-test")
    payload = encode_event(event)
    store.persist(_make_record("dlq-2", event_type=event.event_type, payload=payload))
    bus = InMemoryEventBus()

    viewer_app = _build_app(store=store, auth_enabled=True, roles=["viewer"])
    with TestClient(viewer_app) as client:
        assert client.get("/events/dlq").status_code == 403
        assert client.get("/events/dlq/dlq-1").status_code == 403
        assert client.post("/events/dlq/dlq-1/replay").status_code == 403
        assert client.post("/events/dlq/dlq-1/discard").status_code == 403

    analyst_app = _build_app(store=store, event_bus=bus, auth_enabled=True, roles=["analyst"])
    with TestClient(analyst_app) as client:
        assert client.get("/events/dlq").status_code == 200
        assert client.get("/events/dlq/dlq-1").status_code == 200
        assert client.post("/events/dlq/dlq-1/replay").status_code == 403
        assert client.post("/events/dlq/dlq-1/discard").status_code == 403

    admin_app = _build_app(store=store, event_bus=bus, auth_enabled=True, roles=["admin"])
    with TestClient(admin_app) as client:
        assert client.get("/events/dlq").status_code == 200
        assert client.get("/events/dlq/dlq-1").status_code == 200
        # Verify discard-200 on the first record.
        assert client.post("/events/dlq/dlq-1/discard").status_code == 200
        # Verify replay-200 on the second record (with properly encoded payload).
        replay_response = client.post("/events/dlq/dlq-2/replay")
        assert replay_response.status_code == 200
        assert replay_response.json()["status"] == "replayed"


def _dlq_audit_entries_since(client: TestClient, since: datetime) -> list[dict[str, object]]:
    """`dlq.*` ledger entries recorded at or after `since`.

    Time-scoped rather than counted absolutely: the ledger is Postgres-backed
    in this suite and survives across runs, so `== 1` on a total would pass
    only on a virgin database.
    """
    payload = client.get(
        "/audit/events",
        params={"action_prefix": "dlq.", "from": since.isoformat(), "limit": 200},
    ).json()
    return list(payload["items"])


def test_replay_is_recorded_in_the_audit_ledger() -> None:
    """Replaying a dead-lettered event re-injects it into the pipeline.

    Admin-gated but unattributable until now — `grep -c audit` was 0 in this
    router.
    """
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-audit")
    store = InMemoryDlqRecordStore()
    store.persist(
        _make_record("dlq-a", event_type=event.event_type, payload=encode_event(event))
    )
    app = _build_app(store=store, event_bus=InMemoryEventBus())

    with TestClient(app) as client:
        started = datetime.now(timezone.utc)
        assert client.post("/events/dlq/dlq-a/replay").status_code == 200

        entries = _dlq_audit_entries_since(client, started)

    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "dlq.replay"
    assert entry["resource_type"] == "dlq_record"
    assert entry["resource_id"] == "dlq-a"
    assert entry["before"]["status"] == "pending"
    assert entry["after"]["status"] == "replayed"
    # The stored payload is the original event and may carry KB content; the
    # ledger records who acted on which record, not what the record held.
    assert "payload" not in entry["after"]


def test_discard_is_recorded_in_the_audit_ledger() -> None:
    """Discarding destroys the only operator-visible record of a failure."""
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-audit")
    store = InMemoryDlqRecordStore()
    store.persist(
        _make_record("dlq-b", event_type=event.event_type, payload=encode_event(event))
    )
    app = _build_app(store=store, event_bus=InMemoryEventBus())

    with TestClient(app) as client:
        started = datetime.now(timezone.utc)
        assert client.post("/events/dlq/dlq-b/discard").status_code == 200

        entries = _dlq_audit_entries_since(client, started)

    assert len(entries) == 1
    assert entries[0]["action"] == "dlq.discard"
    assert entries[0]["after"]["status"] == "discarded"


def test_a_losing_concurrent_replay_records_nothing() -> None:
    """The second caller gets 409 and must not claim it replayed anything.

    The entry is written after the CAS for exactly this reason: a ledger that
    recorded both callers would attribute one replay to two operators.
    """
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-audit")
    store = InMemoryDlqRecordStore()
    store.persist(
        _make_record("dlq-c", event_type=event.event_type, payload=encode_event(event))
    )
    app = _build_app(store=store, event_bus=InMemoryEventBus())

    with TestClient(app) as client:
        started = datetime.now(timezone.utc)
        assert client.post("/events/dlq/dlq-c/replay").status_code == 200
        assert client.post("/events/dlq/dlq-c/replay").status_code == 409

        entries = _dlq_audit_entries_since(client, started)

    assert len(entries) == 1
