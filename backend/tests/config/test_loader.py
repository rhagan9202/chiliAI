"""Tests for config.loader — load_config and ConfigLoadError."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from config.loader import ConfigLoadError, load_config
from config.schema import DomainConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"
FOOD_YAML = DEFAULTS_DIR / "food_supply_chain.yaml"


# ---------------------------------------------------------------------------
# load_config from explicit path
# ---------------------------------------------------------------------------


class TestLoadFromPath:
    def test_load_medicare_yaml(self) -> None:
        cfg = load_config(MEDICARE_YAML)
        assert isinstance(cfg, DomainConfig)
        assert cfg.domain.name == "medicare_fraud"
        assert cfg.domain.display_name == "Medicare Fraud Detection"

    def test_load_food_yaml(self) -> None:
        cfg = load_config(FOOD_YAML)
        assert cfg.domain.name == "food_supply_chain"

    def test_entity_names_present(self) -> None:
        cfg = load_config(MEDICARE_YAML)
        names = {e.name for e in cfg.entities}
        assert names == {"provider", "beneficiary", "claim", "facility"}

    def test_relationship_names_present(self) -> None:
        cfg = load_config(MEDICARE_YAML)
        names = {r.name for r in cfg.relationships}
        assert names == {"submitted_by", "billed_for", "performed_at", "referred_by"}

    def test_capabilities(self) -> None:
        cfg = load_config(MEDICARE_YAML)
        assert cfg.capabilities.timeseries is True
        assert cfg.capabilities.gnn is True

    def test_ui_config(self) -> None:
        cfg = load_config(MEDICARE_YAML)
        assert cfg.ui is not None
        assert cfg.ui.default_entity_type == "provider"
        assert cfg.ui.navigation is not None
        assert any(page.id == "alerts" for page in cfg.ui.navigation.pages)

    def test_string_path(self) -> None:
        cfg = load_config(str(MEDICARE_YAML))
        assert cfg.domain.name == "medicare_fraud"


# ---------------------------------------------------------------------------
# load_config from CHILI_CONFIG_PATH env var
# ---------------------------------------------------------------------------


class TestLoadFromEnv:
    def test_load_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHILI_CONFIG_PATH", str(MEDICARE_YAML))
        cfg = load_config()
        assert cfg.domain.name == "medicare_fraud"

    def test_explicit_path_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_CONFIG_PATH", str(MEDICARE_YAML))
        cfg = load_config(FOOD_YAML)
        assert cfg.domain.name == "food_supply_chain"


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------


class TestJsonLoading:
    def test_load_json(self, tmp_path: Path) -> None:
        cfg_yaml = load_config(MEDICARE_YAML)
        json_path = tmp_path / "config.json"
        json_path.write_text(
            json.dumps(cfg_yaml.model_dump(), default=str), encoding="utf-8"
        )
        cfg_json = load_config(json_path)
        assert cfg_json.domain.name == cfg_yaml.domain.name


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestConfigLoadErrors:
    def test_no_path_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CHILI_CONFIG_PATH", raising=False)
        with pytest.raises(ConfigLoadError, match="No config path"):
            load_config()

    def test_file_not_found(self) -> None:
        with pytest.raises(ConfigLoadError, match="not found"):
            load_config("/nonexistent/path.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("key: [\ninvalid:\n  - ]\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="YAML parse error"):
            load_config(bad)

    def test_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="JSON parse error"):
            load_config(bad)

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        bad = tmp_path / "config.toml"
        bad.write_text("x = 1", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="Unsupported"):
            load_config(bad)

    def test_schema_validation_failure(self, tmp_path: Path) -> None:
        partial = tmp_path / "partial.yaml"
        partial.write_text("domain:\n  name: x\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="validation failed"):
            load_config(partial)

    def test_non_mapping_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "list.yaml"
        bad.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="mapping"):
            load_config(bad)
