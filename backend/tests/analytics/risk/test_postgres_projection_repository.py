"""Tests for Postgres-backed risk projection read models."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from types import TracebackType
from typing import cast

from analytics.risk.adapters.postgres import (
    PostgresRiskProjectionRebuildSource,
    PostgresRiskProjectionRepository,
)
from analytics.risk.projections import RiskProjectionQuery, RiskProjectionRow
from database.protocols import ConnectionProvider


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(
        self,
        *,
        rowcount: int = 0,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.rowcount = rowcount
        self._rows = rows or []

    def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self.projection_rows: dict[tuple[str, str], tuple[object, ...]] = {}
        self.rebuild_rows: list[tuple[object, ...]] = []
        self.fail_projection_insert_entity_id: str | None = None
        self._transaction_backup: dict[tuple[str, str], tuple[object, ...]] | None = None

    def execute(
        self, query: str, params: tuple[object, ...] | None = None
    ) -> FakeCursor:
        self.statements.append((query, params))
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("insert into risk_projections"):
            assert params is not None
            self._begin_transaction()
            if self.fail_projection_insert_entity_id == str(params[1]):
                raise RuntimeError("injected projection upsert failure")
            row = _stored_projection_from_insert_params(params)
            self.projection_rows[(str(params[0]), str(params[1]))] = row
            return FakeCursor(rowcount=1)
        if normalized.startswith("delete from risk_projections"):
            assert params is not None
            self._begin_transaction()
            keys = [
                key
                for key in self.projection_rows
                if key[0] == str(params[0])
            ]
            for key in keys:
                del self.projection_rows[key]
            return FakeCursor(rowcount=len(keys))
        if normalized.startswith("select count(*) from risk_projections"):
            assert params is not None
            return FakeCursor(rows=[(len(self._filtered_projection_rows(params)),)])
        if (
            "from risk_projections" in normalized
            and "limit %s offset %s" in normalized
        ):
            assert params is not None
            limit = int(cast(int, params[-2]))
            offset = int(cast(int, params[-1]))
            rows = self._filtered_projection_rows(params[:-2])
            rows.sort(key=lambda row: (-float(cast(float, row[3])), -cast(datetime, row[12]).timestamp(), str(row[1])))
            return FakeCursor(rows=rows[offset : offset + limit])
        if "from risk_projections" in normalized and "where knowledge_base_id = %s and entity_id = %s" in normalized:
            assert params is not None
            row = self.projection_rows.get((str(params[0]), str(params[1])))
            return FakeCursor(rows=[] if row is None else [row])
        if "from risk_projections" in normalized and "where knowledge_base_id = %s" in normalized:
            assert params is not None
            rows = [
                row
                for (knowledge_base_id, _), row in self.projection_rows.items()
                if knowledge_base_id == str(params[0])
            ]
            return FakeCursor(rows=rows)
        if "from risk_score_history" in normalized:
            return FakeCursor(rows=self.rebuild_rows)
        raise AssertionError(f"Unexpected SQL: {query}")

    def _begin_transaction(self) -> None:
        if self._transaction_backup is None:
            self._transaction_backup = dict(self.projection_rows)

    def _filtered_projection_rows(self, params: tuple[object, ...]) -> list[tuple[object, ...]]:
        rows = [
            row
            for (knowledge_base_id, _), row in self.projection_rows.items()
            if knowledge_base_id == str(params[0])
        ]
        for param in params[1:]:
            value = str(param)
            if value in {"provider", "claim", "beneficiary", "organization"}:
                rows = [row for row in rows if row[2] == value]
            elif value in {"low", "medium", "high", "critical"}:
                rows = [row for row in rows if row[4] == value]
            elif value in {"active", "case_open", "resolved", "suppressed", "stale"}:
                rows = [row for row in rows if row[14] == value]
            elif isinstance(param, datetime):
                rows = [row for row in rows if cast(datetime, row[12]) >= param]
            else:
                rows = [
                    row
                    for row in rows
                    if value in json.loads(str(row[5]))
                ]
        return rows

    def commit(self) -> None:
        self.commits += 1
        self._transaction_backup = None

    def rollback(self) -> None:
        self.rollbacks += 1
        if self._transaction_backup is not None:
            self.projection_rows = self._transaction_backup
            self._transaction_backup = None


class FakeContext(AbstractContextManager[FakeConnection]):
    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> FakeConnection:
        return self._conn

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return None


class FakeProvider:
    def __init__(self) -> None:
        self.conn = FakeConnection()

    def connection(self) -> FakeContext:
        return FakeContext(self.conn)

    def close(self) -> None:
        return None


def _row(entity_id: str, *, score: float, scored_at: datetime = NOW) -> RiskProjectionRow:
    return RiskProjectionRow(
        knowledge_base_id="kb-1",
        entity_id=entity_id,
        entity_type="provider",
        overall_score=score,
        risk_level="high" if score >= 0.8 else "medium",
        top_typology_ids=["upcoding"] if score >= 0.8 else ["billing-volume"],
        alert_ids=["alert-1"] if score >= 0.8 else [],
        case_ids=["case-1"] if score >= 0.8 else [],
        evidence_pack_ids=["evidence-1"] if score >= 0.8 else [],
        score_run_id="score-run-1",
        model_version="risk-linear-v1",
        catalog_version="cms-fraud-features-v1",
        scored_at=scored_at,
        updated_at=scored_at,
        status="case_open" if score >= 0.8 else "active",
    )


def _stored_projection_from_insert_params(params: tuple[object, ...]) -> tuple[object, ...]:
    return (
        params[0],
        params[1],
        params[2],
        params[3],
        params[4],
        params[5],
        params[6],
        params[7],
        params[8],
        params[9],
        params[10],
        params[11],
        params[12],
        params[13],
        params[14],
    )


def test_postgres_projection_repository_upserts_lists_and_deletes() -> None:
    provider = FakeProvider()
    repository = PostgresRiskProjectionRepository(cast(ConnectionProvider, provider))

    stored = repository.upsert(_row("provider-1", score=0.91))
    repository.upsert(_row("provider-2", score=0.67))

    assert stored.entity_id == "provider-1"
    insert_statement, insert_params = provider.conn.statements[0]
    assert "%s::jsonb" in insert_statement
    assert insert_params is not None
    json.loads(str(insert_params[5]))
    assert provider.conn.commits == 2

    assert repository.get("kb-1", "provider-1") == _row("provider-1", score=0.91)
    page = repository.list(
        RiskProjectionQuery(
            knowledge_base_id="kb-1",
            risk_level="high",
            typology_id="upcoding",
            status="case_open",
            limit=10,
            offset=0,
        )
    )
    assert page.total == 1
    assert [row.entity_id for row in page.items] == ["provider-1"]
    list_statement, list_params = provider.conn.statements[-1]
    assert "limit %s offset %s" in " ".join(list_statement.split()).lower()
    assert list_params is not None
    assert list_params[-2:] == (10, 0)

    assert [row.entity_id for row in repository.list_all("kb-1")] == [
        "provider-1",
        "provider-2",
    ]
    assert repository.delete_by_kb("kb-1") == 2
    assert repository.list_all("kb-1") == []


def test_postgres_projection_repository_replaces_kb_rows_atomically() -> None:
    provider = FakeProvider()
    repository = PostgresRiskProjectionRepository(cast(ConnectionProvider, provider))
    repository.upsert(_row("provider-1", score=0.91))
    replacement = _row("provider-2", score=0.67)
    provider.conn.fail_projection_insert_entity_id = replacement.entity_id

    try:
        repository.replace_knowledge_base("kb-1", [replacement])
    except Exception as exc:
        assert "Failed to replace risk projections." in str(exc)
    else:  # pragma: no cover - test should fail before this branch
        raise AssertionError("Expected replace_knowledge_base to fail")

    assert provider.conn.rollbacks == 1
    assert repository.get("kb-1", "provider-1") == _row("provider-1", score=0.91)
    assert repository.get("kb-1", "provider-2") is None


def test_postgres_projection_rebuild_source_loads_latest_scores_and_alert_refs() -> None:
    provider = FakeProvider()
    provider.conn.rebuild_rows = [
        (
            "provider-1",
            0.91,
            "high",
            '[{"factor_name": "billing_outlier"}]',
            "score-run-1",
            NOW,
            "provider",
            '["alert-1"]',
            '["evidence-1"]',
            NOW,
        )
    ]
    source = PostgresRiskProjectionRebuildSource(
        cast(ConnectionProvider, provider),
        feature_typology_index={"billing_outlier": ["upcoding"]},
    )

    rows = source.load_projection_rows("kb-1")

    assert len(rows) == 1
    row = rows[0]
    assert row.knowledge_base_id == "kb-1"
    assert row.entity_id == "provider-1"
    assert row.entity_type == "provider"
    assert row.overall_score == 0.91
    assert row.risk_level == "high"
    assert row.top_typology_ids == ["upcoding"]
    assert row.alert_ids == ["alert-1"]
    assert row.evidence_pack_ids == ["evidence-1"]
    assert row.score_run_id == "score-run-1"
    assert row.model_version == "risk-score-history"
    assert row.catalog_version == "risk-score-history"
    assert row.status == "active"
