"""Integration test: the baseline migration creates the full schema."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_EXPECTED_TABLES = {
    "raw_records",
    "observations",
    "entity_metric_history",
    "entity_metrics_current",
    "risk_score_history",
    "alert_history",
}
_EXPECTED_HYPERTABLES = {"observations", "entity_metric_history"}


def _run_migrations(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _run_downgrade(database_url: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_baseline_migration_creates_all_tables(database_url: str) -> None:
    _run_migrations(database_url)
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    try:
        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
            tables = {str(row[0]) for row in rows}
            assert _EXPECTED_TABLES.issubset(tables)

            hyper = conn.execute(
                "SELECT hypertable_name FROM timescaledb_information.hypertables"
            ).fetchall()
            hypertables = {str(row[0]) for row in hyper}
            assert _EXPECTED_HYPERTABLES.issubset(hypertables)
    finally:
        provider.close()


def test_baseline_migration_downgrade_removes_all_tables(database_url: str) -> None:
    _run_migrations(database_url)
    _run_downgrade(database_url)
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    try:
        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
            tables = {str(row[0]) for row in rows}
            assert _EXPECTED_TABLES.isdisjoint(tables)
    finally:
        provider.close()
    _run_migrations(database_url)
