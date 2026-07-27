"""Config-driven entity display labels (UXA-304).

The same entity must render the same name wherever it appears — the alert feed,
the workbench, a case, the chat context rail. That only holds if every producer
resolves the name the same way, from ``ui.display_fields``.
"""

from __future__ import annotations

import pytest

from config.display import entity_display_label
from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    UiConfig,
    UiDisplayFieldsConfig,
)
from shared.types import Entity, EntityDefinition, PropertyDefinition, PropertyType


def _config(display_fields: dict[str, UiDisplayFieldsConfig]) -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(
            name="medicare_fraud", display_name="Medicare Fraud", description=""
        ),
        entities=[
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                natural_key=["npi"],
                properties={
                    "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI"),
                    "name": PropertyDefinition(type=PropertyType.STRING, display="Name"),
                },
            )
        ],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        alerts=AlertsConfig(thresholds={}),
        ui=UiConfig(display_fields=display_fields),
    )


def test_uses_the_configured_title_property() -> None:
    config = _config({"provider": UiDisplayFieldsConfig(title="npi")})
    entity = Entity(id="provider-1", type="provider", properties={"npi": "1234567890"})

    assert entity_display_label(entity, config) == "1234567890"


def test_falls_back_to_a_name_property_when_no_title_is_configured() -> None:
    config = _config({})
    entity = Entity(
        id="provider-1", type="provider", properties={"name": "Redwood DME Group"}
    )

    assert entity_display_label(entity, config) == "Redwood DME Group"


def test_falls_back_to_the_type_label_and_id_when_nothing_names_the_entity() -> None:
    config = _config({"provider": UiDisplayFieldsConfig(title="npi")})
    entity = Entity(id="provider-1", type="provider", properties={})

    assert entity_display_label(entity, config) == "Provider provider-1"


def test_ignores_a_configured_title_property_that_is_blank() -> None:
    config = _config({"provider": UiDisplayFieldsConfig(title="npi")})
    entity = Entity(
        id="provider-1",
        type="provider",
        properties={"npi": "   ", "name": "Redwood DME Group"},
    )

    assert entity_display_label(entity, config) == "Redwood DME Group"


def test_uses_the_raw_type_when_the_entity_type_is_not_declared() -> None:
    config = _config({})
    entity = Entity(id="ghost-1", type="ghost", properties={})

    assert entity_display_label(entity, config) == "ghost ghost-1"


@pytest.mark.parametrize("value", [42, 3.5, True])
def test_stringifies_a_non_string_title_value(value: object) -> None:
    config = _config({"provider": UiDisplayFieldsConfig(title="npi")})
    entity = Entity(id="provider-1", type="provider", properties={"npi": value})

    assert entity_display_label(entity, config) == str(value)
