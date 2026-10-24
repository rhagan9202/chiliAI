"""Tests for the cross-process state-store guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.deployment import process_local_state_stores, require_shared_state_stores
from config.loader import load_config
from config.schema import DatabaseConfig, DomainConfig, GraphDbConfig, VectorStoreConfig
from shared.exceptions import ConfigurationError

_DEFAULTS = Path(__file__).resolve().parents[2] / "config" / "defaults"
_OVERLAYS = Path(__file__).resolve().parents[2] / "config" / "overlays"


def _base_pack() -> DomainConfig:
    return load_config(_DEFAULTS / "medicare_fraud.yaml")


def _shared_pack() -> DomainConfig:
    return _base_pack().model_copy(
        update={
            "database": DatabaseConfig(backend="postgres"),
            "graph": GraphDbConfig(backend="neo4j"),
            "vectorstore": VectorStoreConfig(backend="qdrant"),
        }
    )


def test_base_pack_keeps_every_state_store_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHILI_CONFIG_OVERLAY_PATH", raising=False)

    assert process_local_state_stores(_base_pack()) == [
        "database",
        "graph",
        "vectorstore",
    ]


def test_dev_overlay_moves_every_state_store_out_of_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CHILI_CONFIG_OVERLAY_PATH", str(_OVERLAYS / "medicare_fraud_dev.yaml")
    )

    assert process_local_state_stores(_base_pack()) == []


def test_in_process_event_bus_tolerates_in_memory_stores() -> None:
    # One process (tests, a single-process dev run): in-memory stores are shared.
    require_shared_state_stores(_base_pack(), event_bus_backend="in-memory")


def test_redis_event_bus_rejects_in_memory_stores() -> None:
    """API and worker are separate processes on a Redis bus.

    An in-memory store there is private to each, so the API accepts records
    the worker can never read ("No raw records found"). Fail at boot instead.
    """

    with pytest.raises(ConfigurationError) as exc_info:
        require_shared_state_stores(_base_pack(), event_bus_backend="redis")

    message = str(exc_info.value)
    assert "database, graph, vectorstore" in message
    assert "CHILI_CONFIG_OVERLAY_PATH" in message


def test_redis_event_bus_accepts_shared_stores() -> None:
    require_shared_state_stores(_shared_pack(), event_bus_backend="redis")


def test_a_single_in_memory_store_is_still_rejected() -> None:
    config = _shared_pack().model_copy(
        update={"vectorstore": VectorStoreConfig(backend="in_memory")}
    )

    with pytest.raises(ConfigurationError, match="vectorstore"):
        require_shared_state_stores(config, event_bus_backend="redis")
