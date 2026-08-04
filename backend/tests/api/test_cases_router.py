"""Focused case router tests for historical playbook references."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_alert_feed_store
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.models import AlertHistoryRecord
from shared.utils import utc_now

_PLAYBOOK_REF = {
    "playbook_id": "provider_billing_spike_review",
    "playbook_version": "v1",
    "title": "Provider billing spike review",
}


def _alert_record(
    alert_id: str,
    *,
    playbook_ref: dict[str, str] = _PLAYBOOK_REF,
) -> AlertHistoryRecord:
    now = utc_now()
    return AlertHistoryRecord(
        knowledge_base_id="kb-1",
        alert_id=alert_id,
        entity_id="provider-204",
        entity_type="provider",
        severity="critical",
        status="open",
        title="Outlier billing concentration",
        reasoning="Provider activity is materially above peers.",
        metric_name="claims_per_week",
        evidence_pack_id=f"evidence-{alert_id}",
        created_at=now,
        updated_at=now,
        entity_label="Redwood DME Group",
        confidence=0.96,
        tags=["billing"],
        generation_metadata={"playbook_ref": dict(playbook_ref)},
    )


def _client_with_alerts(records: list[AlertHistoryRecord]) -> TestClient:
    app = create_app()
    store = InMemoryAlertHistoryWriter()
    store.write_alerts(records)
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    return TestClient(app)


def test_case_preserves_playbook_ref_snapshot() -> None:
    client = _client_with_alerts([_alert_record("alert-001")])

    promoted = client.post(
        "/cases/promote",
        params={"knowledge_base_id": "kb-1"},
        json={"alert_id": "alert-001"},
    )

    assert promoted.status_code == 200
    case = promoted.json()["case"]
    assert case["playbook_ref"] == _PLAYBOOK_REF

    detail = client.get(f"/cases/{case['id']}", params={"knowledge_base_id": "kb-1"})
    assert detail.status_code == 200
    assert detail.json()["case"]["playbook_ref"] == _PLAYBOOK_REF

    listed = client.get("/cases", params={"knowledge_base_id": "kb-1"})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["playbook_ref"] == _PLAYBOOK_REF


def test_new_playbook_version_does_not_rewrite_existing_case_ref() -> None:
    new_playbook_ref = {
        "playbook_id": "provider_billing_spike_review",
        "playbook_version": "v2",
        "title": "Provider billing spike review",
    }
    client = _client_with_alerts(
        [
            _alert_record("alert-001"),
            _alert_record("alert-002", playbook_ref=new_playbook_ref),
        ]
    )
    kb = {"knowledge_base_id": "kb-1"}

    promoted = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"})
    assert promoted.status_code == 200
    case_id = promoted.json()["case"]["id"]

    attached = client.post(
        f"/cases/{case_id}/alerts",
        params=kb,
        json={"alert_id": "alert-002"},
    )

    assert attached.status_code == 200
    assert attached.json()["case"]["playbook_ref"] == _PLAYBOOK_REF
    detail = client.get(f"/cases/{case_id}", params=kb)
    assert detail.status_code == 200
    assert detail.json()["case"]["playbook_ref"] == _PLAYBOOK_REF


def test_create_case_rejects_client_supplied_playbook_ref() -> None:
    client = _client_with_alerts([])

    response = client.post(
        "/cases",
        params={"knowledge_base_id": "kb-1"},
        json={
            "title": "Untrusted provenance",
            "priority": "medium",
            "playbook_ref": _PLAYBOOK_REF,
        },
    )

    assert response.status_code == 422
