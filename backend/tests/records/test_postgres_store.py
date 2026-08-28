"""Integration tests for the Postgres raw record store."""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from records.adapters.postgres import PostgresRawRecordStore
from records.models import RawRecord, RawRecordKey, content_hash_for

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
        assert store.persist([]) == []

        inserted = store.persist(
            [
                _record("claim-1", correlation_id=correlation_id),
                _record("claim-2", correlation_id=correlation_id),
            ]
        )
        assert inserted == [
            RawRecordKey("claim_record", "claim-1"),
            RawRecordKey("claim_record", "claim-2"),
        ]

        # Idempotent re-persist inserts nothing, so RETURNING yields no key.
        assert store.persist([_record("claim-1", correlation_id=correlation_id)]) == []

        loaded = store.load_batch(
            knowledge_base_id="kb-records-test", correlation_id=correlation_id
        )
        assert [record.record_id for record in loaded] == ["claim-1", "claim-2"]
        assert loaded[0].payload["amount"] == 12.5

        # KB-wide load returns the same rows without needing a correlation id.
        kb_loaded = store.load_for_kb(knowledge_base_id="kb-records-test")
        assert [record.record_id for record in kb_loaded] == ["claim-1", "claim-2"]
        assert kb_loaded[0].payload["amount"] == 12.5
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()
        provider.close()


def test_submission_dedup_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRawRecordStore(provider)
    submission_hash = "sub-hash-records-store-1"
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM record_submissions "
                "WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()

        assert (
            store.was_submitted(
                knowledge_base_id="kb-records-test", submission_hash=submission_hash
            )
            is False
        )
        store.record_submission(
            knowledge_base_id="kb-records-test",
            submission_hash=submission_hash,
            correlation_id="corr-dedup-1",
        )
        assert (
            store.was_submitted(
                knowledge_base_id="kb-records-test", submission_hash=submission_hash
            )
            is True
        )
        # Re-recording the same submission hash is a no-op (ON CONFLICT).
        store.record_submission(
            knowledge_base_id="kb-records-test",
            submission_hash=submission_hash,
            correlation_id="corr-dedup-2",
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM record_submissions "
                "WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()
        provider.close()


def test_delete_by_kb_clears_both_tables(database_url: str) -> None:
    """delete_by_kb removes raw_records AND record_submissions for the KB."""
    kb_id = "kb-delete-by-kb-test"
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRawRecordStore(provider)
    try:
        # Seed: one raw_record and one submission hash for the KB.
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.execute(
                "DELETE FROM record_submissions WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()

        store.persist([_record("rec-1", correlation_id="corr-delbykb")])
        # Override kb_id to our unique test KB.
        with provider.connection() as conn:
            conn.execute(
                "UPDATE raw_records SET knowledge_base_id = %s "
                "WHERE knowledge_base_id = 'kb-records-test' AND record_id = 'rec-1'",
                (kb_id,),
            )
            conn.commit()
        store.record_submission(
            knowledge_base_id=kb_id,
            submission_hash="sub-delbykb-1",
            correlation_id="corr-delbykb",
        )

        # Verify seed is in place.
        with provider.connection() as conn:
            rr_count = conn.execute(
                "SELECT COUNT(*) FROM raw_records WHERE knowledge_base_id = %s", (kb_id,)
            ).fetchone()
            rs_count = conn.execute(
                "SELECT COUNT(*) FROM record_submissions WHERE knowledge_base_id = %s",
                (kb_id,),
            ).fetchone()
        assert rr_count is not None and rr_count[0] == 1
        assert rs_count is not None and rs_count[0] == 1

        # delete_by_kb must atomically remove both.
        removed = store.delete_by_kb(kb_id)
        assert removed == 1

        with provider.connection() as conn:
            rr_after = conn.execute(
                "SELECT COUNT(*) FROM raw_records WHERE knowledge_base_id = %s", (kb_id,)
            ).fetchone()
            rs_after = conn.execute(
                "SELECT COUNT(*) FROM record_submissions WHERE knowledge_base_id = %s",
                (kb_id,),
            ).fetchone()
        assert rr_after is not None and rr_after[0] == 0, "raw_records not cleared"
        assert rs_after is not None and rs_after[0] == 0, "record_submissions not cleared"
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.execute(
                "DELETE FROM record_submissions WHERE knowledge_base_id = %s", (kb_id,)
            )
            conn.commit()
        provider.close()


def test_rollback_removes_only_this_batch_and_frees_the_submission(
    database_url: str,
) -> None:
    """``delete_records`` / ``discard_submission`` back out one failed attempt.

    The service calls these when a publish fails after the rows are committed.
    Rows landed by an earlier call must survive, and the submission hash must
    stop suppressing the client's retry.

    The surviving rows here share the failed attempt's **correlation id** on
    purpose: a connector sync run assigns one correlation id and reuses it for
    every page, so giving each batch its own id would test a situation the
    connector path never produces and would pass against a rollback that wipes
    the whole run.
    """
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    store = PostgresRawRecordStore(provider)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.execute(
                "DELETE FROM record_submissions "
                "WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()

        run_correlation_id = "corr-sync-run"
        store.persist([_record("keep-1", correlation_id=run_correlation_id)])
        failed_page = store.persist(
            [_record("rollback-1", correlation_id=run_correlation_id)]
        )
        store.record_submission(
            knowledge_base_id="kb-records-test",
            submission_hash="hash-rollback",
            correlation_id=run_correlation_id,
        )
        assert store.was_submitted(
            knowledge_base_id="kb-records-test", submission_hash="hash-rollback"
        )

        removed = store.delete_records(
            knowledge_base_id="kb-records-test", keys=failed_page
        )
        store.discard_submission(
            knowledge_base_id="kb-records-test", submission_hash="hash-rollback"
        )

        assert removed == 1
        surviving = store.load_batch(
            knowledge_base_id="kb-records-test", correlation_id=run_correlation_id
        )
        assert [record.record_id for record in surviving] == ["keep-1"]
        assert not store.was_submitted(
            knowledge_base_id="kb-records-test", submission_hash="hash-rollback"
        )
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.execute(
                "DELETE FROM record_submissions "
                "WHERE knowledge_base_id = 'kb-records-test'"
            )
            conn.commit()
