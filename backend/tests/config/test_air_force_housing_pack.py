from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import load_config
from config.schema import DomainConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = (
    REPO_ROOT
    / "backend"
    / "config"
    / "defaults"
    / "department_air_force_housing.yaml"
)


@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch) -> DomainConfig:
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(PACK_PATH))
    return load_config()


def test_air_force_housing_pack_loads(config: DomainConfig) -> None:
    assert config.domain.name == "department_air_force_housing"
    assert config.domain.display_name == "Department of the Air Force Housing"
    assert config.capabilities.structured_ingestion is True
    assert config.capabilities.rag_chat is True


def test_housing_entities_and_relationships_are_declared(config: DomainConfig) -> None:
    entity_names = {entity.name for entity in config.entities}
    assert {
        "installation",
        "housing_asset",
        "housing_inventory_snapshot",
        "population_demand_snapshot",
        "allowance_market_snapshot",
        "demographic_snapshot",
        "resident_experience_snapshot",
        "scorecard_run",
    } <= entity_names
    relationship_names = {relationship.name for relationship in config.relationships}
    assert {
        "installation_has_asset",
        "asset_has_inventory_snapshot",
        "installation_has_population_demand",
        "installation_has_market_snapshot",
        "installation_has_demographic_snapshot",
        "scorecard_run_for_installation",
    } <= relationship_names


def test_housing_record_feeds_cover_required_exports(config: DomainConfig) -> None:
    assert config.records is not None
    feeds = {feed.name: feed for feed in config.records.feeds}
    assert {
        "umd_authorizations",
        "bah_rates",
        "housing_inventory",
        "market_availability",
        "area_demographics",
    } <= set(feeds)
    assert feeds["umd_authorizations"].accepted_formats == ["csv", "jsonl"]
    assert feeds["housing_inventory"].allow_extra_fields is True
    for feed in feeds.values():
        assert feed.entities
        assert feed.observations


def test_scorecard_templates_are_configured(config: DomainConfig) -> None:
    template_ids = {template.id for template in config.scorecards.templates}
    assert {"uh_scorecard", "mfh_scorecard"} <= template_ids
    for template in config.scorecards.templates:
        assert template.sections
        assert template.export_formats == ["json", "markdown"]
        for section in template.sections:
            assert section.metrics
            for metric in section.metrics:
                assert metric.inputs
                assert metric.formula.operator in {
                    "ratio",
                    "sum",
                    "mean",
                    "weighted_mean",
                    "latest",
                }
                assert (
                    metric.thresholds.pass_min is not None
                    or metric.thresholds.fail_max is not None
                )


def test_housing_ui_lands_on_housing_page(config: DomainConfig) -> None:
    assert config.ui is not None
    pages = (
        {page.id: page for page in config.ui.navigation.pages}
        if config.ui.navigation
        else {}
    )
    assert pages["housing"].route == "/housing"
    assert config.ui.roles["executive"].landing_page == "housing"
