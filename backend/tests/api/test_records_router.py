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


def test_upload_jsonl_file_returns_a_receipt(client: TestClient) -> None:
    import json

    row = {
        "claim_id": "c1",
        "provider_npi": "1234567890",
        "billed_amount": 99.0,
        "service_date": "2026-01-15",
        "anomaly_score": 0.8,
    }
    jsonl_body = json.dumps(row).encode()
    response = client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.jsonl", io.BytesIO(jsonl_body), "application/x-ndjson")},
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


def test_upload_rejects_file_exceeding_size_limit() -> None:
    # Load the real medicare_fraud config and override only the validation
    # section with max_file_size_mb=1 (minimum valid value).  Then upload a
    # file slightly larger than 1 MB to trigger the HTTP 413 branch.
    from pathlib import Path
    from fastapi.testclient import TestClient as TC

    from api.app import create_app
    from api.dependencies import get_domain_config, get_raw_record_store
    from config.loader import load_config
    from config.schema import ValidationConfig

    import pytest as _pytest

    defaults_dir = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    base = load_config(defaults_dir / "medicare_fraud.yaml")
    tiny_config = base.model_copy(update={"validation": ValidationConfig(max_file_size_mb=1)})

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_domain_config] = lambda: tiny_config
        tiny_client = TC(app)

    # 1 MB + 1 byte exceeds the 1 MB limit.
    oversized = b"a" * (1 * 1024 * 1024 + 1)
    response = tiny_client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.csv", io.BytesIO(oversized), "text/csv")},
    )
    assert response.status_code == 413


def test_upload_file_feed_not_found_returns_404(client: TestClient) -> None:
    from unittest.mock import MagicMock
    from records.exceptions import RecordFeedNotFoundError
    from records.protocols import RecordsServiceProtocol
    from api.dependencies import get_records_service

    mock_service = MagicMock(spec=RecordsServiceProtocol)
    mock_service.register_records.side_effect = RecordFeedNotFoundError("ghost_feed")

    from fastapi.testclient import TestClient as TC
    import pytest as _pytest
    from api.app import create_app
    from api.dependencies import get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_records_service] = lambda: mock_service
        err_client = TC(app)

    csv_body = "claim_id,provider_npi,billed_amount,service_date,anomaly_score\nc1,1234567890,99.0,2026-01-15,0.8\n"
    response = err_client.post(
        "/records/kb-1/files",
        data={"feed": "ghost_feed"},
        files={"file": ("claims.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert response.status_code == 404


def test_upload_file_persistence_error_returns_500(client: TestClient) -> None:
    from unittest.mock import MagicMock
    from records.exceptions import RecordPersistenceError
    from records.protocols import RecordsServiceProtocol
    from api.dependencies import get_records_service

    mock_service = MagicMock(spec=RecordsServiceProtocol)
    mock_service.register_records.side_effect = RecordPersistenceError("DB down")

    from fastapi.testclient import TestClient as TC
    import pytest as _pytest
    from api.app import create_app
    from api.dependencies import get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_records_service] = lambda: mock_service
        err_client = TC(app)

    csv_body = "claim_id,provider_npi,billed_amount,service_date,anomaly_score\nc1,1234567890,99.0,2026-01-15,0.8\n"
    response = err_client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert response.status_code == 500


def test_upload_file_records_error_returns_422(client: TestClient) -> None:
    from unittest.mock import MagicMock
    from records.exceptions import RecordsError
    from records.protocols import RecordsServiceProtocol
    from api.dependencies import get_records_service

    mock_service = MagicMock(spec=RecordsServiceProtocol)
    mock_service.register_records.side_effect = RecordsError("bad row data")

    from fastapi.testclient import TestClient as TC
    import pytest as _pytest
    from api.app import create_app
    from api.dependencies import get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_records_service] = lambda: mock_service
        err_client = TC(app)

    csv_body = "claim_id,provider_npi,billed_amount,service_date,anomaly_score\nc1,1234567890,99.0,2026-01-15,0.8\n"
    response = err_client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.csv", io.BytesIO(csv_body.encode()), "text/csv")},
    )
    assert response.status_code == 422


def test_push_records_persistence_error_returns_500(client: TestClient) -> None:
    from unittest.mock import MagicMock
    from records.exceptions import RecordPersistenceError
    from records.protocols import RecordsServiceProtocol
    from api.dependencies import get_records_service

    mock_service = MagicMock(spec=RecordsServiceProtocol)
    mock_service.register_records.side_effect = RecordPersistenceError("storage failure")

    from fastapi.testclient import TestClient as TC
    import pytest as _pytest
    from api.app import create_app
    from api.dependencies import get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_records_service] = lambda: mock_service
        err_client = TC(app)

    response = err_client.post(
        "/records/kb-1/push",
        json={"feed_name": "claims_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 500


def test_push_records_records_error_returns_422(client: TestClient) -> None:
    from unittest.mock import MagicMock
    from records.exceptions import RecordsError
    from records.protocols import RecordsServiceProtocol
    from api.dependencies import get_records_service

    mock_service = MagicMock(spec=RecordsServiceProtocol)
    mock_service.register_records.side_effect = RecordsError("generic records error")

    from fastapi.testclient import TestClient as TC
    import pytest as _pytest
    from api.app import create_app
    from api.dependencies import get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", "config/defaults/medicare_fraud.yaml")
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_records_service] = lambda: mock_service
        err_client = TC(app)

    response = err_client.post(
        "/records/kb-1/push",
        json={"feed_name": "claims_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 422
