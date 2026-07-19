"""Integration tests for the Postgres peerstats adapters (require a live DB)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import cast

import pytest

from analytics.peerstats.adapters.postgres import (
    PostgresDerivedRiskSignalWriter,
    PostgresRecordColumnSource,
)
from analytics.peerstats.models import DerivedRiskSignal
from config.schema import DatabaseConfig, PeerMetricSpec
from database.protocols import DatabaseConnection
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration

_KB = "kb-peerstats-test"


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping peerstats adapter test.")
    return url


def _spec() -> PeerMetricSpec:
    return PeerMetricSpec(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
    )


def _insert_record(
    conn: DatabaseConnection,
    *,
    record_id: str,
    npi: str,
    amount: str,
    ingested_at: datetime,
    service_date: str | None = None,
    knowledge_base_id: str = _KB,
) -> None:
    fields: dict[str, str] = {"provider_npi": npi, "billed_amount": amount}
    if service_date is not None:
        fields["service_date"] = service_date
    payload = json.dumps(fields)
    conn.execute(
        "INSERT INTO raw_records (knowledge_base_id, record_type, record_id, "
        "payload, source_type, correlation_id, content_hash, ingested_at) "
        "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)",
        (
            knowledge_base_id,
            "claim_record",
            record_id,
            payload,
            "file_upload",
            "corr-1",
            f"hash-{knowledge_base_id}-{record_id}",
            ingested_at,
        ),
    )


def test_aggregate_and_write_round_trip(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    source = PostgresRecordColumnSource(provider)
    writer = PostgresDerivedRiskSignalWriter(provider)
    monday = datetime(2026, 1, 5, tzinfo=timezone.utc)
    wednesday = datetime(2026, 1, 7, tzinfo=timezone.utc)
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = %s", (_KB,)
            )
            conn.execute(
                "DELETE FROM entity_derived_signals WHERE knowledge_base_id = %s",
                (_KB,),
            )
            conn.commit()
        with provider.connection() as conn:
            _insert_record(conn, record_id="r1", npi="1", amount="10",
                           ingested_at=monday)
            _insert_record(conn, record_id="r2", npi="1", amount="5",
                           ingested_at=wednesday)
            _insert_record(conn, record_id="r3", npi="2", amount="3",
                           ingested_at=monday)
            # A non-numeric value that must be skipped, not abort the batch.
            _insert_record(conn, record_id="r4", npi="3", amount="N/A",
                           ingested_at=monday)
            conn.commit()

        aggregates = source.load_interval_aggregates(
            knowledge_base_id=_KB, spec=_spec(), interval_starts=[monday]
        )
        by_entity = {a.entity_id: a.aggregate_value for a in aggregates}
        assert by_entity == {"provider:1": 15.0, "provider:2": 3.0}
        assert all(a.peer_group_key == "provider" for a in aggregates)

        signal = DerivedRiskSignal(
            knowledge_base_id=_KB, entity_id="provider:1", entity_type="provider",
            metric_name="weekly_billing", interval_start=monday,
            peer_group_key="provider", aggregate_value=15.0, peer_mean=9.0,
            peer_std=6.0, z_score=1.0, signal_value=0.25, weight=1.0,
            rationale="x", correlation_id="corr-1",
        )
        assert writer.write_signals([signal]) == 1
        # Idempotent upsert: re-writing the same key does not duplicate.
        assert writer.write_signals([signal]) == 1
        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM entity_derived_signals "
                "WHERE knowledge_base_id = %s AND entity_id = %s",
                (_KB, "provider:1"),
            ).fetchall()
            assert int(cast(int, rows[0][0])) == 1

        # delete_by_kb purges all derived signals for the KB.
        assert writer.delete_by_kb(_KB) == 1
        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM entity_derived_signals "
                "WHERE knowledge_base_id = %s",
                (_KB,),
            ).fetchall()
            assert int(cast(int, rows[0][0])) == 0
        # Idempotent: deleting again removes nothing.
        assert writer.delete_by_kb(_KB) == 0
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = %s", (_KB,)
            )
            conn.execute(
                "DELETE FROM entity_derived_signals WHERE knowledge_base_id = %s",
                (_KB,),
            )
            conn.commit()
        provider.close()


_KB_TIME_COLUMN = "kb-peerstats-time-column-test"


def test_aggregate_skips_rows_missing_time_column(database_url: str) -> None:
    """Regression test for the live B2 failure: a record whose optional
    time_column key is entirely absent from the JSONB payload must be
    excluded from aggregation, not blow up ``load_interval_aggregates``
    with a NULL ``interval_start`` (Pydantic validation failure on
    ``PeerAggregate``)."""

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    source = PostgresRecordColumnSource(provider)
    monday = datetime(2026, 1, 5, tzinfo=timezone.utc)
    spec = PeerMetricSpec(
        name="weekly_billing_dated",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
        time_column="service_date",
    )
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = %s",
                (_KB_TIME_COLUMN,),
            )
            conn.commit()
        with provider.connection() as conn:
            # Dated rows: aggregated normally.
            _insert_record(
                conn, record_id="t1", npi="1", amount="10", ingested_at=monday,
                service_date="2026-01-05T00:00:00Z",
                knowledge_base_id=_KB_TIME_COLUMN,
            )
            _insert_record(
                conn, record_id="t2", npi="2", amount="7", ingested_at=monday,
                service_date="2026-01-06T00:00:00Z",
                knowledge_base_id=_KB_TIME_COLUMN,
            )
            # Dateless row: key entirely absent (the live TN DE-SynPUF case).
            # Must be skipped rather than aborting the whole batch.
            _insert_record(
                conn, record_id="t3", npi="3", amount="99", ingested_at=monday,
                service_date=None,
                knowledge_base_id=_KB_TIME_COLUMN,
            )
            conn.commit()

        aggregates = source.load_interval_aggregates(
            knowledge_base_id=_KB_TIME_COLUMN, spec=spec, interval_starts=[]
        )
        by_entity = {a.entity_id: a.aggregate_value for a in aggregates}
        assert by_entity == {"provider:1": 10.0, "provider:2": 7.0}
        assert "provider:3" not in by_entity
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM raw_records WHERE knowledge_base_id = %s",
                (_KB_TIME_COLUMN,),
            )
            conn.commit()
        provider.close()
