"""Tests for PostgresRiskSignalSource using a fake connection provider."""

from __future__ import annotations

import pytest

from analytics.risk.adapters.postgres import PostgresRiskSignalSource


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _sql: str, _params: object = None) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def commit(self) -> None:
        return None


class _FakeProvider:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def connection(self) -> _FakeConn:
        return _FakeConn(self._rows)


def test_load_profile_builds_signals_from_rows() -> None:
    # rows: (metric_name, signal_value, weight, rationale)
    rows: list[tuple[object, ...]] = [
        ("weekly_billing", 0.4, 1.5, "weekly_billing: z=1.60 vs provider peers"),
        ("weekly_claim_count", 0.2, 1.0, "weekly_claim_count: z=0.80 vs provider peers"),
    ]
    source = PostgresRiskSignalSource(_FakeProvider(rows))  # type: ignore[arg-type]
    profile = source.load_profile(knowledge_base_id="kb1", entity_id="provider:1")
    assert {s.signal_name for s in profile.signals} == {
        "weekly_billing", "weekly_claim_count"
    }
    billing = next(s for s in profile.signals if s.signal_name == "weekly_billing")
    assert billing.value == 0.4
    assert billing.weight == 1.5


def test_load_profile_raises_when_no_signals() -> None:
    source = PostgresRiskSignalSource(_FakeProvider([]))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        source.load_profile(knowledge_base_id="kb1", entity_id="provider:404")


def test_list_ranked_entries_derives_entity_type_and_filters() -> None:
    # rows: (entity_id, overall_score, risk_level)
    rows: list[tuple[object, ...]] = [
        ("provider:1", 0.9, "high"),
        ("provider:2", 0.4, "low"),
    ]
    source = PostgresRiskSignalSource(_FakeProvider(rows))  # type: ignore[arg-type]
    entries = source.list_ranked_entries(
        knowledge_base_id="kb1", entity_type="provider", limit=10
    )
    assert [e.entity_id for e in entries] == ["provider:1", "provider:2"]
    assert all(e.entity_type == "provider" for e in entries)
    # entity_type filter that matches nothing returns empty
    none = source.list_ranked_entries(
        knowledge_base_id="kb1", entity_type="claim", limit=10
    )
    assert none == []


def test_load_historical_score_returns_latest() -> None:
    rows: list[tuple[object, ...]] = [(0.73,)]
    source = PostgresRiskSignalSource(_FakeProvider(rows))  # type: ignore[arg-type]
    assert source.load_historical_score(
        knowledge_base_id="kb1", entity_id="provider:1"
    ) == 0.73
