"""Tests for config.loader — load_config and ConfigLoadError."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from config.loader import ConfigLoadError, load_config
from config.schema import DomainConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"
FOOD_YAML = DEFAULTS_DIR / "food_supply_chain.yaml"


def _load_default(name: str) -> DomainConfig:
    """Load a named pack from config/defaults/<name>.yaml."""
    return load_config(DEFAULTS_DIR / f"{name}.yaml")


# ---------------------------------------------------------------------------
# Round-trip test: every YAML in config/defaults/ must load without error.
# This guards against schema drift whenever a new config block is added.
# ---------------------------------------------------------------------------


def _all_default_yamls() -> list[Path]:
    return sorted(DEFAULTS_DIR.glob("*.yaml"))


def _minimal_config_dict() -> dict[str, object]:
    return {
        "domain": {"name": "minimal", "display_name": "Minimal", "description": "d"},
        "entities": [
            {
                "name": "thing",
                "display_label": "Thing",
                "icon": "box",
                "properties": {
                    "thing_id": {"type": "string", "display": "ID", "required": True}
                },
            }
        ],
        "relationships": [],
        "capabilities": {},
        "ingestion": {"sources": [{"type": "file_upload", "formats": ["csv"]}]},
        "alerts": {"thresholds": {}},
    }


def _write_minimal_config(path: Path) -> Path:
    path.write_text(yaml.safe_dump(_minimal_config_dict()), encoding="utf-8")
    return path


@pytest.mark.parametrize("yaml_path", _all_default_yamls(), ids=lambda p: p.name)
def test_all_defaults_load_successfully(yaml_path: Path) -> None:
    cfg = load_config(yaml_path)
    assert isinstance(cfg, DomainConfig), f"{yaml_path.name} did not produce a DomainConfig"
    assert cfg.domain.name, f"{yaml_path.name}: domain.name must be non-empty"
    assert cfg.entities, f"{yaml_path.name}: entities list must be non-empty"


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


def test_medicare_ships_policy_rules() -> None:
    cfg = load_config(MEDICARE_YAML)
    assert cfg.policy_rules, "medicare_fraud.yaml must ship at least one policy rule pack"
    rule = cfg.policy_rules[0].rules[0]
    assert rule.predicate.op in {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"}


def test_food_supply_ships_policy_rules() -> None:
    cfg = load_config(FOOD_YAML)
    assert cfg.policy_rules, "food_supply_chain.yaml must ship at least one policy rule pack"


def test_policy_rules_default_to_empty_when_block_absent(tmp_path: Path) -> None:
    # additive/optional — a config without a policy_rules block defaults to [].
    minimal: dict[str, object] = {
        "domain": {"name": "minimal", "display_name": "Minimal", "description": "d"},
        "entities": [
            {
                "name": "thing",
                "display_label": "Thing",
                "icon": "box",
                "properties": {
                    "thing_id": {"type": "string", "display": "ID", "required": True}
                },
            }
        ],
        "relationships": [],
        "capabilities": {},
        "ingestion": {"sources": [{"type": "file_upload", "formats": ["csv"]}]},
        "alerts": {"thresholds": {}},
    }
    path = tmp_path / "minimal.json"
    path.write_text(json.dumps(minimal), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.policy_rules == []


def test_medicare_fraud_pack_declares_typologies_and_features() -> None:
    cfg = _load_default("medicare_fraud")

    assert len(cfg.typologies) >= 8
    assert len(cfg.feature_catalog.features) >= 20
    assert {typology.id for typology in cfg.typologies} >= {
        "dmepos_overutilization",
        "billing_spike",
        "peer_outlier",
        "referral_ring_exposure",
        "geographic_anomaly",
        "enrollment_risk",
        "never_provided_service",
        "policy_threshold_exposure",
    }


def test_medicare_fraud_pack_declares_seed_playbooks() -> None:
    cfg = load_config(DEFAULTS_DIR / "medicare_fraud.yaml")

    seed_ids = {
        "provider_billing_spike_review",
        "peer_outlier_provider_review",
        "identity_mismatch_review",
    }
    playbooks = {playbook.id: playbook for playbook in cfg.playbooks.items}
    assert set(playbooks) >= seed_ids
    referenced = {
        playbook_id
        for typology in cfg.typologies
        for playbook_id in typology.playbook_ids
    }
    assert referenced <= set(playbooks)
    for playbook_id in seed_ids:
        playbook = playbooks[playbook_id]
        assert playbook.evidence_requirements
        assert playbook.workflow_steps
        assert playbook.rag_prompts
        assert playbook.decision_guidance
        assert playbook.export_tags


# ---------------------------------------------------------------------------
# CHILI_CONFIG_OVERLAY_PATH env overlay wiring (BL-044, config.04)
# ---------------------------------------------------------------------------


def test_load_config_applies_env_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    overlay_path = tmp_path / "dev-overlay.yaml"
    overlay_path.write_text(
        yaml.safe_dump(
            {"overlay_for": base_path.stem, "capabilities": {"rag_chat": False}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(overlay_path))
    config = load_config(base_path)
    assert config.capabilities.rag_chat is False


def test_load_config_overlay_env_unset_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    monkeypatch.delenv("CHILI_CONFIG_OVERLAY_PATH", raising=False)
    config = load_config(base_path)  # must not raise
    assert config.domain.name


def test_load_config_overlay_error_becomes_config_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    bad_overlay = tmp_path / "bad.yaml"
    bad_overlay.write_text(
        yaml.safe_dump({"capabilities": {}}), encoding="utf-8"
    )  # no overlay_for
    monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(bad_overlay))
    with pytest.raises(ConfigLoadError, match="overlay_for"):
        load_config(base_path)


def test_load_config_overlay_paths_comma_separated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    stem = base_path.stem
    a = tmp_path / "a.yaml"
    a.write_text(
        yaml.safe_dump({"overlay_for": stem, "capabilities": {"gnn": False}}),
        encoding="utf-8",
    )
    b = tmp_path / "b.yaml"
    b.write_text(
        yaml.safe_dump({"overlay_for": stem, "capabilities": {"gnn": True}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", f" {a} , {b} ")
    config = load_config(base_path)
    assert config.capabilities.gnn is True


# ---------------------------------------------------------------------------
# Domain pack timeseries/peer_stats declarations (B2, sprint 2026-28 Task 7)
# ---------------------------------------------------------------------------


def test_cms_pack_declares_peerstats_and_timeseries() -> None:
    config = _load_default("medicare_fraud_cms_desynpuf")
    assert config.capabilities.peer_stats is True
    assert config.peer_stats is not None and len(config.peer_stats.metrics) == 2
    assert {cohort.id for cohort in config.peer_stats.cohorts} == {
        "provider_specialty_carrier_billing",
        "provider_geography_carrier_billing",
        "provider_service_mix_inpatient_billing",
    }
    assert config.timeseries is not None
    names = [spec.name for spec in config.timeseries.metrics]
    assert names == ["weekly_carrier_billing_self", "monthly_inpatient_billing_self"]


def test_housing_pack_declares_timeseries() -> None:
    config = _load_default("department_air_force_housing")
    assert config.capabilities.timeseries is True
    assert config.timeseries is not None
    assert config.timeseries.metrics[0].name == "monthly_affordability_trend"


# ---------------------------------------------------------------------------
# Domain pack explainability backend declarations (B3, sprint 2026-28 Task 7)
# ---------------------------------------------------------------------------


def test_cms_pack_enables_llm_narrative_and_shap_attribution() -> None:
    config = _load_default("medicare_fraud_cms_desynpuf")
    assert config.analytics is not None
    assert config.analytics.narrative_backend == "llm"
    assert config.analytics.attribution_backend == "shap"


def test_housing_pack_enables_llm_narrative_and_shap_attribution() -> None:
    config = _load_default("department_air_force_housing")
    assert config.analytics is not None
    assert config.analytics.narrative_backend == "llm"
    assert config.analytics.attribution_backend == "shap"


# ---------------------------------------------------------------------------
# Analyst role dashboard access (alerts.36) — the CMS/food/legacy medicare
# packs all route a `dashboard` nav page; the analyst role must be able to
# reach it now that the alert feed's durable read model makes dashboard
# metrics meaningful for analysts, not just supervisors. Housing has no
# `dashboard` nav page and is intentionally excluded — roles are allowed to
# differ across packs by design, this only pins the three edited packs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pack_name",
    ["medicare_fraud", "medicare_fraud_cms_desynpuf", "food_supply_chain"],
)
def test_analyst_role_includes_dashboard(pack_name: str) -> None:
    config = _load_default(pack_name)
    assert config.ui is not None and config.ui.roles is not None
    analyst = config.ui.roles["analyst"]
    assert "dashboard" in analyst.pages, (
        f"{pack_name}: analyst role must include 'dashboard' in pages"
    )
