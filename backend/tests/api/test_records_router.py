"""Tests for the records ingestion API router."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_raw_record_store
from records.adapters.in_memory import InMemoryRawRecordStore


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv(
        "CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml"
    )
    app = create_app()
    # Inject a fresh in-memory store per test so that lru_cached singletons do
    # not cause cross-test record deduplication (e.g. record c1 inserted in the
    # push test would prevent the CSV upload test from seeing accepted_count=1).
    app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
    return TestClient(app)


def test_push_records_returns_a_receipt(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c1",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["accepted_count"] == 1
    assert body["record_type"] == "claim_record"


def test_push_records_rejects_unknown_feed(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/push",
        json={"feed_name": "ghost_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 404


def test_push_records_rejects_invalid_rows(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/push",
        json={"feed_name": "claims_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 422


def test_upload_csv_file_returns_a_receipt(client: TestClient) -> None:
    csv_body = (
        "claim_id,provider_npi,billed_amount,service_date,anomaly_score\n"
        "c1,1234567890,99.0,2026-01-15,0.8\n"
    )
    response = client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert response.status_code == 202, response.text
    assert response.json()["accepted_count"] == 1


def test_upload_rejects_unsupported_file_type(client: TestClient) -> None:
    response = client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert response.status_code == 415
