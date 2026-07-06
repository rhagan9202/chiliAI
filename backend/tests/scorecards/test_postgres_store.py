from __future__ import annotations

import json
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime
from types import TracebackType
from typing import cast

from database.protocols import ConnectionProvider
from scorecards.adapters.postgres import PostgresScorecardRunRepository
from scorecards.models import ScorecardMetricResult, ScorecardRun, ScorecardSectionResult


NOW = datetime(2026, 7, 1, tzinfo=UTC)


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
        self._stored: tuple[object, ...] | None = None
        self.delete_count = 0

    def execute(
        self, query: str, params: tuple[object, ...] | None = None
    ) -> FakeCursor:
        self.statements.append((query, params))
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("insert into scorecard_runs"):
            if self._stored is None:
                assert params is not None
                self._stored = _row_from_insert_params(params)
                return FakeCursor(rowcount=1)
            return FakeCursor(rowcount=0)
        if "select count(*) from scorecard_runs" in normalized:
            return FakeCursor(rows=[(1 if self._stored is not None else 0,)])
        if normalized.startswith("select"):
            return FakeCursor(rows=[] if self._stored is None else [self._stored])
        if normalized.startswith("delete from scorecard_runs"):
            count = self.delete_count
            self._stored = None
            return FakeCursor(rowcount=count)
        raise AssertionError(f"Unexpected SQL: {query}")

    def commit(self) -> None:
        self.commits += 1


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


def _run(run_id: str = "run-1") -> ScorecardRun:
    metric = ScorecardMetricResult(
        id="uh_supply_ratio",
        label="UH Supply Ratio",
        value=None,
        health="incomplete",
        completeness="missing_source",
        warnings=["Missing required source records for housing_inventory."],
    )
    return ScorecardRun(
        id=run_id,
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        template_name="Unaccompanied Housing Scorecard",
        scope_type="installation",
        scope_id="jbsa",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        source_snapshot_hash="snapshot-a",
        overall_health="incomplete",
        sections=[
            ScorecardSectionResult(
                id="demand_supply",
                label="Demand And Supply",
                metrics=[metric],
            )
        ],
        export_payloads={"json": "{}", "markdown": "# Scorecard"},
        created_at=NOW,
        updated_at=NOW,
    )


def _row_from_insert_params(params: tuple[object, ...]) -> tuple[object, ...]:
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


def test_upsert_inserts_jsonb_payloads_then_returns_existing_on_conflict() -> None:
    provider = FakeProvider()
    repo = PostgresScorecardRunRepository(cast(ConnectionProvider, provider))

    first = repo.upsert(_run("run-1"))
    second = repo.upsert(_run("run-2").model_copy(update={"template_name": "Changed"}))

    assert first.id == "run-1"
    assert second.id == "run-1"
    insert_statement, insert_params = provider.conn.statements[0]
    assert "%s::jsonb" in insert_statement
    assert insert_params is not None
    json.loads(str(insert_params[11]))
    json.loads(str(insert_params[12]))
    assert provider.conn.commits == 2


def test_get_list_and_delete_by_kb_use_kb_scoped_contract() -> None:
    provider = FakeProvider()
    repo = PostgresScorecardRunRepository(cast(ConnectionProvider, provider))
    repo.upsert(_run("run-1"))

    assert repo.get(knowledge_base_id="kb-1", run_id="run-1") is not None
    items, total = repo.list(
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        status="generated",
        limit=10,
        offset=0,
    )
    assert total == 1
    assert [item.id for item in items] == ["run-1"]

    provider.conn.delete_count = 1
    assert repo.delete_by_kb("kb-1") == 1
