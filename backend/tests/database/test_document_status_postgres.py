"""Integration tests: Postgres document status store monotonic upsert (BL-041)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore
from ingestion.models import DocumentStatusTransition, IngestionStatus

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 1, 12, 1, tzinfo=UTC)
T2 = datetime(2026, 7, 1, 12, 2, tzinfo=UTC)
T3 = datetime(2026, 7, 1, 12, 3, tzinfo=UTC)


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(
        DatabaseConfig(backend="postgres")
    )
    assert connection_provider is not None
    with connection_provider.connection() as conn:
        conn.execute("DELETE FROM source_document_status")
        conn.commit()
    yield connection_provider
    connection_provider.close()


def _transition(
    status: IngestionStatus,
    *,
    doc: str = "doc-1",
    occurred_at: datetime = T0,
    error: str | None = None,
    dropped_entities: int | None = None,
    reasons: list[str] | None = None,
) -> DocumentStatusTransition:
    return DocumentStatusTransition(
        knowledge_base_id="kb-pg",
        source_document_id=doc,
        status=status,
        error_message=error,
        dropped_entity_count=dropped_entities,
        sample_reasons=reasons,
        occurred_at=occurred_at,
    )


def test_stale_parsing_after_failed_is_ignored(provider: ConnectionProvider) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(_transition(IngestionStatus.PARSED, occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="boom")
    )
    record = store.apply(_transition(IngestionStatus.PARSING, occurred_at=T2))

    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "boom"
    assert record.first_event_at == T0


def test_warning_counts_persist_and_overwrite(provider: ConnectionProvider) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(
        _transition(
            IngestionStatus.EXTRACTED_EMPTY,
            occurred_at=T1,
            dropped_entities=4,
            reasons=["entity cand-1: unknown type"],
        )
    )
    replay = store.apply(
        _transition(
            IngestionStatus.EXTRACTED_EMPTY,
            occurred_at=T1,
            dropped_entities=4,
            reasons=["entity cand-1: unknown type"],
        )
    )
    assert replay.current_status == IngestionStatus.EXTRACTED_EMPTY
    assert replay.dropped_entity_count == 4
    assert replay.sample_reasons == ["entity cand-1: unknown type"]

    fetched = store.get_many(
        knowledge_base_id="kb-pg", source_document_ids=["doc-1"]
    )
    assert fetched["doc-1"] == replay


def test_list_filters_by_status_and_delete_by_kb(
    provider: ConnectionProvider,
) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1", occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-2", occurred_at=T1, error="x")
    )

    failed, total = store.list(
        knowledge_base_id="kb-pg",
        limit=10,
        offset=0,
        status=IngestionStatus.FAILED,
    )
    assert total == 1
    assert failed[0].source_document_id == "doc-2"

    everything, all_total = store.list(
        knowledge_base_id="kb-pg", limit=10, offset=0
    )
    assert all_total == 2
    assert [row.source_document_id for row in everything] == ["doc-2", "doc-1"]

    assert store.delete_by_kb("kb-pg") == 2
    assert store.list(knowledge_base_id="kb-pg", limit=10, offset=0) == ([], 0)


def test_delete_by_document_removes_only_that_row(
    provider: ConnectionProvider,
) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1", occurred_at=T0))
    store.apply(
        _transition(IngestionStatus.FAILED, doc="doc-2", occurred_at=T1, error="x")
    )

    assert store.delete_by_document("kb-pg", "doc-1") is True

    remaining, total = store.list(knowledge_base_id="kb-pg", limit=10, offset=0)
    assert total == 1
    assert [row.source_document_id for row in remaining] == ["doc-2"]


def test_delete_by_document_returns_false_for_missing_row(
    provider: ConnectionProvider,
) -> None:
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(_transition(IngestionStatus.PARSED, doc="doc-1", occurred_at=T0))

    assert store.delete_by_document("kb-pg", "doc-missing") is False
    assert store.delete_by_document("kb-missing", "doc-1") is False


def test_failed_redelivery_refreshes_last_error(
    provider: ConnectionProvider,
) -> None:
    """Corrected semantics: last_error is not gated on strictly-greater rank.

    A second FAILED at the same (max) rank must overwrite the stored error
    with the newer message.
    """
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="first failure")
    )
    record = store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T2, error="second failure")
    )

    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "second failure"
    assert record.updated_at == T2


def test_stale_lower_rank_after_failed_leaves_error_untouched(
    provider: ConnectionProvider,
) -> None:
    """A lower-rank event arriving after FAILED must never touch last_error."""
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="first failure")
    )
    record = store.apply(
        _transition(IngestionStatus.PARSING, occurred_at=T2, error="stale noise")
    )

    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "first failure"


def test_failed_with_null_error_preserves_stored_error(
    provider: ConnectionProvider,
) -> None:
    """A FAILED transition with no error_message must not wipe a stored one."""
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="first failure")
    )
    record = store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T2, error=None)
    )

    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "first failure"
    # updated_at still advances even though last_error did not change.
    assert record.updated_at == T2


def test_failed_then_parsed_then_second_failed_refreshes_error(
    provider: ConnectionProvider,
) -> None:
    """Sanity check across three transitions to guard the full FAILED->FAILED path."""
    store = PostgresSourceDocumentStatusStore(provider)
    store.apply(
        _transition(IngestionStatus.PARSED, occurred_at=T0)
    )
    store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T1, error="first failure")
    )
    store.apply(
        _transition(IngestionStatus.PARSING, occurred_at=T2, error="stale noise")
    )
    record = store.apply(
        _transition(IngestionStatus.FAILED, occurred_at=T3, error="second failure")
    )

    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "second failure"
    assert record.first_event_at == T0
    assert record.updated_at == T3
