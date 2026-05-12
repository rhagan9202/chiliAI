"""Shared backend pytest configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "defaults"
    / "medicare_fraud.yaml"
)


@pytest.fixture(autouse=True)
def default_chili_config_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give tests a deterministic domain config unless a case overrides it."""

    monkeypatch.setenv("CHILI_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
    monkeypatch.setenv("CHILI_ENV", "local")
