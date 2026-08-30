"""Integration tests for the Postgres raw record store."""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
import records.adapters.postgres as postgres_module
from records.adapters.postgres import PostgresRawRecordStore
from records.exceptions import RecordPersistenceError
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


def test_rollback_submission_removes_only_this_batch_and_frees_the_submission(
    database_url: str,
) -> None:
    """``rollback_submission`` backs out one failed attempt: the rows this
    call inserted go, rows an earlier call landed stay, and the submission
    hash stops suppressing the client's retry.

    The surviving row here shares the failed attempt's **correlation id** on
    purpose: a connector sync run assigns one correlation id and reuses it for
    every page, so giving each batch its own id would test a situation the
    connector path never produces and would pass against a rollback that wipes
    the whole run.

    This asserts the *effects*. That they land in one transaction is asserted
    separately by
    ``test_rollback_submission_rolls_the_deletes_back_if_the_discard_fails``.
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

        run_correlation_id = "corr-sync-run-atomic"
        store.persist([_record("keep-2", correlation_id=run_correlation_id)])
        failed_page = store.persist(
            [_record("rollback-2", correlation_id=run_correlation_id)]
        )
        store.record_submission(
            knowledge_base_id="kb-records-test",
            submission_hash="hash-rollback-atomic",
            correlation_id=run_correlation_id,
        )
        assert store.was_submitted(
            knowledge_base_id="kb-records-test", submission_hash="hash-rollback-atomic"
        )

        removed = store.rollback_submission(
            knowledge_base_id="kb-records-test",
            keys=failed_page,
            submission_hash="hash-rollback-atomic",
        )

        assert removed == 1
        surviving = store.load_batch(
            knowledge_base_id="kb-records-test", correlation_id=run_correlation_id
        )
        assert [record.record_id for record in surviving] == ["keep-2"]
        assert not store.was_submitted(
            knowledge_base_id="kb-records-test", submission_hash="hash-rollback-atomic"
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
        provider.close()


def test_rollback_submission_rolls_the_deletes_back_if_the_discard_fails(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The atomicity claim, asserted rather than inferred.

    ``test_rollback_submission_removes_only_this_batch_and_frees_the_submission``
    checks that both effects landed -- which a two-transaction implementation
    would satisfy identically. The property that actually matters is the
    negative one: if the second statement fails, the first must not survive,
    because rows-deleted-with-hash-retained is the state that makes the
    client's retry a permanent no-op.

    Forces exactly that by making the discard statement invalid SQL, then
    asserts the row deletes that ran before it were rolled back. Without
    ``psycopg``'s ``with conn:`` transaction scope around both statements this
    fails with the row gone and the hash intact -- the precise defect
    records.18 closed.
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

        correlation_id = "corr-sync-run-atomic-fault"
        failed_page = store.persist(
            [_record("rollback-3", correlation_id=correlation_id)]
        )
        store.record_submission(
            knowledge_base_id="kb-records-test",
            submission_hash="hash-rollback-fault",
            correlation_id=correlation_id,
        )

        monkeypatch.setattr(
            postgres_module,
            "_DISCARD_SUBMISSION_SQL",
            "DELETE FROM record_submissions WHERE no_such_column = %s AND %s IS NOT NULL",
        )

        with pytest.raises(RecordPersistenceError):
            store.rollback_submission(
                knowledge_base_id="kb-records-test",
                keys=failed_page,
                submission_hash="hash-rollback-fault",
            )

        surviving = store.load_batch(
            knowledge_base_id="kb-records-test", correlation_id=correlation_id
        )
        assert [record.record_id for record in surviving] == ["rollback-3"], (
            "the row delete committed even though the hash discard failed -- "
            "the two statements are not in one transaction"
        )
        assert store.was_submitted(
            knowledge_base_id="kb-records-test", submission_hash="hash-rollback-fault"
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
