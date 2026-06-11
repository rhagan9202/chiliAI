"""Tests for the records ingestion API router."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_knowledge_base_repository, get_raw_record_store
from knowledgebases import InMemoryKnowledgeBaseRepository
from records.adapters.in_memory import InMemoryRawRecordStore
from shared.types import KnowledgeBase


_MEDICARE_CONFIG_PATH = str(
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "defaults"
    / "medicare_fraud.yaml"
)


def _knowledge_base(knowledge_base_id: str = "kb-1") -> KnowledgeBase:
    return KnowledgeBase(
        id=knowledge_base_id,
        name="Test KB",
        description="Test knowledge base",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _seeded_repository() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(_knowledge_base())
    return repository


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
    app = create_app()
    # Inject a fresh in-memory store per test so that lru_cached singletons do
    # not cause cross-test record deduplication (e.g. record c1 inserted in the
    # push test would prevent the CSV upload test from seeing accepted_count=1).
    app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
    app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
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


def test_push_records_reports_invalid_rows_as_rejected(client: TestClient) -> None:
    """Per-row format-rejection: a bad row is reported, not raised (BL-015)."""
    response = client.post(
        "/records/kb-1/push",
        json={"feed_name": "claims_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["accepted_count"] == 0
    assert body["rejected_count"] == 1
    assert body["rejected"][0]["index"] == 0


def test_push_records_duplicate_resubmission_returns_200(
    monkeypatch: pytest.MonkeyPatch,
    complete_inflight_workflows: Callable[[TestClient], None],
) -> None:
    """A re-pushed identical batch is a duplicate no-op at HTTP 200 (BL-015).

    The first push starts a workflow run (one per KB); the duplicate-200
    guarantee holds once the KB is idle, so we finish the run before resubmit.
    """
    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
    app = create_app()
    # A single shared store instance so submission dedup persists across the two
    # requests (the default fixture builds a fresh store per request).
    shared_store = InMemoryRawRecordStore()
    app.dependency_overrides[get_raw_record_store] = lambda: shared_store
    app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
    shared_client = TestClient(app)

    payload = {
        "feed_name": "claims_feed",
        "rows": [
            {
                "claim_id": "c-dup",
                "provider_npi": "1234567890",
                "billed_amount": 99.0,
                "service_date": "2026-01-15",
                "anomaly_score": 0.8,
            }
        ],
    }
    first = shared_client.post("/records/kb-1/push", json=payload)
    assert first.status_code == 202, first.text
    assert first.json()["duplicate"] is False

    # Finish the run started by the first push so the KB is idle for the retry.
    complete_inflight_workflows(shared_client)

    second = shared_client.post("/records/kb-1/push", json=payload)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["duplicate"] is True
    assert body["accepted_count"] == 0
    assert body["duplicate_count"] == 1


def test_push_records_rejects_missing_knowledge_base(client: TestClient) -> None:
    response = client.post(
        "/records/missing-kb/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c-missing",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )

    assert response.status_code == 404


def test_push_records_rejects_busy_knowledge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient as TC
    from api.app import create_app
    from api.dependencies import (
        get_knowledge_base_repository,
        get_raw_record_store,
        get_workflow_tracker,
    )

    class BusyTracker:
        def is_busy(self, knowledge_base_id: str) -> bool:
            return knowledge_base_id == "kb-1"

    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
    app = create_app()
    app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
    app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
    app.dependency_overrides[get_workflow_tracker] = lambda: BusyTracker()
    test_client = TC(app)

    response = test_client.post(
        "/records/kb-1/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c-busy",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )

    assert response.status_code == 409


def test_push_records_rejects_pending_cleanup_knowledge_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient as TC
    from api.app import create_app
    from api.dependencies import get_knowledge_base_repository, get_raw_record_store

    repository = _seeded_repository()
    repository.mark_pending_cleanup("kb-1")

    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
    app = create_app()
    app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    test_client = TC(app)

    response = test_client.post(
        "/records/kb-1/push",
        json={
            "feed_name": "claims_feed",
            "rows": [
                {
                    "claim_id": "c-cleanup",
                    "provider_npi": "1234567890",
                    "billed_amount": 99.0,
                    "service_date": "2026-01-15",
                    "anomaly_score": 0.8,
                }
            ],
        },
    )

    assert response.status_code == 409


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


def test_upload_rejects_format_not_in_feed_accepted_formats() -> None:
    """A feed that only accepts csv rejects a jsonl upload with HTTP 415 (BL-015)."""
    from fastapi.testclient import TestClient as TC

    from api.app import create_app
    from api.dependencies import get_domain_config, get_raw_record_store
    from config.loader import load_config

    base = load_config(Path(_MEDICARE_CONFIG_PATH))
    assert base.records is not None
    feeds = base.records.feeds
    csv_only_feeds = [
        feed.model_copy(update={"accepted_formats": ["csv"]})
        if feed.name == "claims_feed"
        else feed
        for feed in feeds
    ]
    csv_only_config = base.model_copy(
        update={"records": base.records.model_copy(update={"feeds": csv_only_feeds})}
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
        app.dependency_overrides[get_domain_config] = lambda: csv_only_config
        csv_only_client = TC(app)

    import json

    row = {
        "claim_id": "c1",
        "provider_npi": "1234567890",
        "billed_amount": 99.0,
        "service_date": "2026-01-15",
        "anomaly_score": 0.8,
    }
    response = csv_only_client.post(
        "/records/kb-1/files",
        data={"feed": "claims_feed"},
        files={"file": ("claims.jsonl", io.BytesIO(json.dumps(row).encode()), "application/x-ndjson")},
    )
    assert response.status_code == 415, response.text


def test_upload_rejects_file_exceeding_size_limit() -> None:
    # Load the real medicare_fraud config and override only the validation
    # section with max_file_size_mb=1 (minimum valid value).  Then upload a
    # file slightly larger than 1 MB to trigger the HTTP 413 branch.
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
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
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
    from api.dependencies import get_knowledge_base_repository, get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
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
    from api.dependencies import get_knowledge_base_repository, get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
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
    from api.dependencies import get_knowledge_base_repository, get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
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
    from api.dependencies import get_knowledge_base_repository, get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
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
    from api.dependencies import get_knowledge_base_repository, get_raw_record_store

    with _pytest.MonkeyPatch.context() as mp:
        mp.setenv("CHILI_ENV", "local")
        mp.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
        app = create_app()
        app.dependency_overrides[get_raw_record_store] = InMemoryRawRecordStore
        app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
        app.dependency_overrides[get_records_service] = lambda: mock_service
        err_client = TC(app)

    response = err_client.post(
        "/records/kb-1/push",
        json={"feed_name": "claims_feed", "rows": [{"claim_id": "c1"}]},
    )
    assert response.status_code == 422


def test_push_records_starts_one_tracked_workflow(
    monkeypatch: pytest.MonkeyPatch,
    complete_inflight_workflows: Callable[[TestClient], None],
) -> None:
    """A successful push starts exactly one service-tracked run; a later
    duplicate (post-completion) does not add a second."""
    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv("CHILI_CONFIG_PATH", _MEDICARE_CONFIG_PATH)
    app = create_app()
    shared_store = InMemoryRawRecordStore()
    app.dependency_overrides[get_raw_record_store] = lambda: shared_store
    app.dependency_overrides[get_knowledge_base_repository] = _seeded_repository
    client = TestClient(app)

    payload = {
        "feed_name": "claims_feed",
        "rows": [
            {
                "claim_id": "c-wf",
                "provider_npi": "1234567890",
                "billed_amount": 50.0,
                "service_date": "2026-01-15",
                "anomaly_score": 0.5,
            }
        ],
    }
    assert client.post("/records/kb-1/push", json=payload).status_code == 202

    listed = client.get("/workflows", params={"knowledge_base_id": "kb-1"})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "running"
    assert items[0]["knowledge_base_id"] == "kb-1"

    # A duplicate resubmission (after the run finishes) starts no new run.
    complete_inflight_workflows(client)
    assert client.post("/records/kb-1/push", json=payload).status_code == 200
    again = client.get("/workflows", params={"knowledge_base_id": "kb-1"})
    assert len(again.json()["items"]) == 1
