"""Integration tests for the Postgres raw record store."""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from records.adapters.postgres import PostgresRawRecordStore
from records.models import RawRecord, content_hash_for

pytestmark = pytest.mark.integration


def _record(record_id: str, *, correlation_id: str) -> RawRecord:
    payload: dict[str, object] = {"claim_id": record_id, "amount": 12.5}
    return RawRecord(
        knowledge_base_id="kb-records-test",
        record_type="claim_record",
        record_id=record_id,
        payload=payload,
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id=correlation_id,
        content_hash=content_hash_for(payload),
    )


def test_persist_and_load_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRawRecordStore(provider)
    correlation_id = "corr-records-store-1"
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()

        # Empty batch short-circuits before touching the DB.
        assert store.persist([]) == 0

        inserted = store.persist(
            [
                _record("claim-1", correlation_id=correlation_id),
                _record("claim-2", correlation_id=correlation_id),
            ]
        )
        assert inserted == 2

        # Idempotent re-persist inserts nothing.
        assert store.persist([_record("claim-1", correlation_id=correlation_id)]) == 0

        loaded = store.load_batch(
            knowledge_base_id="kb-records-test", correlation_id=correlation_id
        )
        assert [record.record_id for record in loaded] == ["claim-1", "claim-2"]
        assert loaded[0].payload["amount"] == 12.5
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()
        provider.close()
