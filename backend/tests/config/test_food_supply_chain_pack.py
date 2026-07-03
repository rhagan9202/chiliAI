"""Validation tests for the food_supply_chain domain pack.

The pack must be a first-class peer of the medicare exemplar: it has to load
through ``load_config`` (exercising the full ``DomainConfig`` cross-validator,
including records-feed referential checks), carry a complete ``ui`` section so
the frontend renders it without code changes, and pin real infra backends
matching the dev stack.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.loader import load_config
from config.schema import DomainConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = REPO_ROOT / "backend" / "config" / "defaults" / "food_supply_chain.yaml"


@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch) -> DomainConfig:
    """Load the pack exactly as the app does: via CHILI_CONFIG_PATH."""
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(PACK_PATH))
    return load_config()


def test_pack_loads_via_env_path(config: DomainConfig) -> None:
    assert config.domain.name == "food_supply_chain"
    assert config.domain.display_name
    assert config.domain.description


def test_entities_cover_supply_chain_and_compliance(config: DomainConfig) -> None:
    entity_names = {entity.name for entity in config.entities}
    assert {
        "supplier",
        "facility",
        "product_lot",
        "shipment",
        "inspection",
        "lab_test",
        "contaminant",
        "recall",
    } <= entity_names
    for entity in config.entities:
        assert entity.natural_key, f"Entity '{entity.name}' has no natural_key."
        for key_field in entity.natural_key:
            assert key_field in entity.properties, (
                f"Entity '{entity.name}' natural_key field '{key_field}' "
                "is not a declared property."
            )


def test_relationship_referential_integrity(config: DomainConfig) -> None:
    entity_names = {entity.name for entity in config.entities}
    relationship_names = {rel.name for rel in config.relationships}
    assert {
        "shipped_by",
        "shipped_from",
        "contains_lot",
        "produced_at",
        "supplied_by",
        "inspected_at",
        "tested_lot",
        "detected",
        "recalled_lot",
        "issued_against",
        "subcontracts",
    } <= relationship_names
    for rel in config.relationships:
        assert rel.source in entity_names
        assert rel.target in entity_names


def test_records_feeds_pass_cross_validation(config: DomainConfig) -> None:
    assert config.records is not None
    feeds = config.records.feeds
    feed_names = {feed.name for feed in feeds}
    assert {
        "shipments_feed",
        "inspections_feed",
        "lab_results_feed",
        "recalls_feed",
    } <= feed_names
    assert len(feeds) >= 2

    entity_names = {entity.name for entity in config.entities}
    relationship_names = {rel.name for rel in config.relationships}
    for feed in feeds:
        schema_fields = set(feed.record_schema.keys())
        assert feed.id_field in schema_fields
        mapped_types = {mapping.entity_type for mapping in feed.entities}
        assert mapped_types <= entity_names
        for mapping in feed.entities:
            assert mapping.id_field in schema_fields
            for record_field in mapping.property_fields.values():
                assert record_field in schema_fields, (
                    f"Feed '{feed.name}' maps entity property from unknown "
                    f"record field '{record_field}'."
                )
        for rel_mapping in feed.relationships:
            assert rel_mapping.relationship_type in relationship_names
            assert rel_mapping.source_entity_type in mapped_types
            assert rel_mapping.target_entity_type in mapped_types
        for observation in feed.observations:
            assert observation.entity_type in mapped_types
            assert observation.score_field in schema_fields


def test_every_feed_emits_graph_structure(config: DomainConfig) -> None:
    assert config.records is not None
    for feed in config.records.feeds:
        assert feed.entities, f"Feed '{feed.name}' maps no entities."
        assert feed.relationships, f"Feed '{feed.name}' maps no relationships."
        assert feed.observations, f"Feed '{feed.name}' emits no observations."


def test_ui_section_is_complete(config: DomainConfig) -> None:
    ui = config.ui
    assert ui is not None
    entity_names = {entity.name for entity in config.entities}

    assert ui.default_entity_type in entity_names

    assert ui.navigation is not None
    pages = ui.navigation.pages
    assert pages
    page_ids = {page.id for page in pages}
    assert {"dashboard", "alerts", "knowledge_bases", "configuration"} <= page_ids
    capability_flags = set(config.capabilities.model_dump().keys())
    for page in pages:
        assert page.route.startswith("/")
        if page.capability is not None:
            assert page.capability in capability_flags

    # Every declared entity renders: display_fields cover the full entity set
    # and reference real properties.
    assert set(ui.display_fields.keys()) == entity_names
    for entity in config.entities:
        fields = ui.display_fields[entity.name]
        assert fields.title in entity.properties
        if fields.subtitle is not None:
            assert fields.subtitle in entity.properties
        for chip in fields.chips:
            assert chip in entity.properties

    assert ui.roles
    for role_name, role in ui.roles.items():
        assert role.landing_page in page_ids, (
            f"Role '{role_name}' landing page '{role.landing_page}' "
            "is not a navigation page."
        )
        assert set(role.pages) <= page_ids


def test_alert_thresholds_reference_declared_entities(config: DomainConfig) -> None:
    entity_names = {entity.name for entity in config.entities}
    assert config.alerts.thresholds
    assert set(config.alerts.thresholds.keys()) <= entity_names


def test_policy_rule_packs_present(config: DomainConfig) -> None:
    pack_ids = {pack.id for pack in config.policy_rules}
    assert {"facility_compliance", "contamination_watch", "graph_scale_watch"} <= pack_ids
    entity_names = {entity.name for entity in config.entities}
    for pack in config.policy_rules:
        for rule in pack.rules:
            if rule.target_kind == "entity":
                assert rule.target_selector.get("entity_type") in entity_names


def test_infra_backends_match_dev_stack(config: DomainConfig) -> None:
    assert config.graph is not None and config.graph.backend == "neo4j"
    assert config.graph.uri == "bolt://neo4j:7687"
    assert config.vectorstore is not None and config.vectorstore.backend == "qdrant"
    assert config.vectorstore.uri == "http://qdrant:6333"
    assert config.events is not None and config.events.backend == "redis"
    assert config.events.uri == "redis://redis:6379"
    assert config.database is not None and config.database.backend == "postgres"
    assert config.storage is not None and config.storage.backend == "local"
    assert config.llm is not None and config.llm.provider == "local"
    assert config.embeddings is not None
    assert config.vectorstore.dimensions == config.embeddings.dimensions
    assert config.monitoring is not None
    assert config.analytics is not None


def test_capabilities_enable_structured_ingestion(config: DomainConfig) -> None:
    assert config.capabilities.structured_ingestion is True
    assert config.capabilities.risk_scoring is True
    assert config.capabilities.rag_chat is True


# ---------------------------------------------------------------------------
# Switch ergonomics: CHILI_CONFIG_PATH must be parameterized (with the
# medicare exemplar as default) in BOTH compose services of BOTH files, so a
# single env var retargets api and worker together.
# ---------------------------------------------------------------------------

CONFIG_PATH_ENTRY = (
    "CHILI_CONFIG_PATH="
    "${CHILI_CONFIG_PATH:-/app/config/defaults/medicare_fraud_cms_desynpuf.yaml}"
)


@pytest.mark.parametrize(
    "compose_file", ["docker-compose.dev.yaml", "docker-compose.yaml"]
)
def test_compose_parameterizes_config_path(compose_file: str) -> None:
    compose_path = REPO_ROOT / compose_file
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    for service_name in ("api", "worker"):
        environment = compose["services"][service_name]["environment"]
        assert CONFIG_PATH_ENTRY in environment, (
            f"{compose_file} service '{service_name}' must parameterize "
            "CHILI_CONFIG_PATH with the medicare pack as default."
        )
