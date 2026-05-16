"""Tests for DatabaseConfig schema and DomainConfig wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.schema import DatabaseConfig


def test_defaults() -> None:
    config = DatabaseConfig()
    assert config.backend == "in_memory"
    assert config.dsn_env_var == "DATABASE_URL"
    assert config.pool_size == 10
    assert config.pool_max_overflow == 5
    assert config.statement_timeout_ms == 30000


def test_postgres_backend_is_accepted() -> None:
    config = DatabaseConfig(backend="postgres")
    assert config.backend == "postgres"


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabaseConfig(backend="mysql")  # type: ignore[arg-type]


def test_pool_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        DatabaseConfig(pool_size=0)


def test_domain_config_defaults_database_section() -> None:
    from config.loader import load_config  # noqa: PLC0415

    defaults_path = (
        Path(__file__).parent.parent.parent / "config" / "defaults" / "medicare_fraud.yaml"
    )
    config = load_config(defaults_path)
    assert config.database is not None
    assert config.database.backend == "in_memory"
