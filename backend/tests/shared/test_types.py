"""Tests for the shared types module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shared.types import (
    Alert,
    Entity,
    EntityDefinition,
    EvidencePack,
    KnowledgeBase,
    PropertyDefinition,
    PropertyType,
    Relationship,
    RelationshipDefinition,
    validate_entity,
)
from shared.utils import generate_id, normalize_text


# ---------------------------------------------------------------------------
# PropertyType enum
# ---------------------------------------------------------------------------


class TestPropertyType:
    def test_all_values(self) -> None:
        expected = {
            "string",
            "integer",
            "decimal",
            "date",
            "list",
            "boolean",
            "enum",
            "nested",
        }
        assert {m.value for m in PropertyType} == expected

    def test_from_string(self) -> None:
        assert PropertyType("string") is PropertyType.STRING
        assert PropertyType("enum") is PropertyType.ENUM


# ---------------------------------------------------------------------------
# PropertyDefinition / EntityDefinition / RelationshipDefinition
# ---------------------------------------------------------------------------


class TestConfigDefinitionTypes:
    def test_property_definition(self) -> None:
        prop = PropertyDefinition(type=PropertyType.STRING, display="NPI")
        assert prop.type is PropertyType.STRING
        assert prop.display == "NPI"
        assert prop.enum_values is None

    def test_property_definition_with_enum_values(self) -> None:
        prop = PropertyDefinition(
            type=PropertyType.ENUM,
            display="Status",
            enum_values=["active", "inactive"],
        )
        assert prop.enum_values == ["active", "inactive"]

    def test_entity_definition(self) -> None:
        defn = EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={
                "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI"),
            },
        )
        assert defn.name == "provider"
        assert "npi" in defn.properties

    def test_entity_definition_roundtrip(self) -> None:
        defn = EntityDefinition(
            name="claim",
            display_label="Claim",
            icon="document",
            properties={
                "amount": PropertyDefinition(
                    type=PropertyType.DECIMAL, display="Billed Amount"
                ),
            },
        )
        data = defn.model_dump()
        restored = EntityDefinition.model_validate(data)
        assert restored == defn

    def test_relationship_definition(self) -> None:
        rel = RelationshipDefinition(
            name="submitted_by",
            display_label="Submitted By",
            source="claim",
            target="provider",
        )
        assert rel.source == "claim"
        assert rel.target == "provider"

    def test_relationship_definition_roundtrip(self) -> None:
        rel = RelationshipDefinition(
            name="billed_for",
            display_label="Billed For",
            source="claim",
            target="beneficiary",
        )
        data = rel.model_dump()
        restored = RelationshipDefinition.model_validate(data)
        assert restored == rel


# ---------------------------------------------------------------------------
# Generic runtime types
# ---------------------------------------------------------------------------


class TestEntity:
    def test_construct_minimal(self) -> None:
        e = Entity(id="e1", type="provider")
        assert e.properties == {}
        assert e.metadata == {}

    def test_construct_full(self) -> None:
        e = Entity(
            id="e2",
            type="claim",
            properties={"amount": 150.00},
            metadata={"source": "csv"},
        )
        assert e.properties["amount"] == 150.00


class TestRelationship:
    def test_construct(self) -> None:
        r = Relationship(
            id="r1",
            type="submitted_by",
            source_id="claim1",
            target_id="provider1",
        )
        assert r.source_id == "claim1"
        assert r.properties == {}


# ---------------------------------------------------------------------------
# Platform types
# ---------------------------------------------------------------------------


class TestAlert:
    def test_construct(self) -> None:
        now = datetime.now(tz=timezone.utc)
        a = Alert(
            id="a1",
            entity_type="provider",
            entity_id="p1",
            severity="high",
            title="Anomalous billing",
            reasoning="Billing volume exceeded threshold.",
            created_at=now,
        )
        assert a.acknowledged is False
        assert a.evidence_pack_id is None


class TestEvidencePack:
    def test_construct(self) -> None:
        ep = EvidencePack(
            id="ep1",
            alert_id="a1",
            reasoning="Cluster analysis",
            subgraph_nodes=["n1", "n2"],
            subgraph_edges=["e1"],
            confidence=0.92,
        )
        assert ep.confidence == 0.92
        assert ep.scores == {}


class TestKnowledgeBase:
    def test_construct(self) -> None:
        now = datetime.now(tz=timezone.utc)
        kb = KnowledgeBase(
            id="kb1",
            name="Medicare Policies",
            description="CMS policy docs",
            created_at=now,
        )
        assert kb.entity_count == 0
        assert kb.status == "active"


# ---------------------------------------------------------------------------
# validate_entity helper
# ---------------------------------------------------------------------------


class TestValidateEntity:
    @pytest.fixture()
    def entity_defs(self) -> list[EntityDefinition]:
        return [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                properties={
                    "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI"),
                    "specialty": PropertyDefinition(
                        type=PropertyType.STRING, display="Specialty"
                    ),
                },
            ),
        ]

    def test_valid_entity(self, entity_defs: list[EntityDefinition]) -> None:
        e = Entity(id="1", type="provider", properties={"npi": "123"})
        assert validate_entity(e, entity_defs) == []

    def test_unknown_type(self, entity_defs: list[EntityDefinition]) -> None:
        e = Entity(id="1", type="unknown")
        errors = validate_entity(e, entity_defs)
        assert len(errors) == 1
        assert "Unknown entity type" in errors[0]

    def test_extra_property(self, entity_defs: list[EntityDefinition]) -> None:
        e = Entity(id="1", type="provider", properties={"npi": "123", "bogus": "x"})
        errors = validate_entity(e, entity_defs)
        assert any("Unexpected property 'bogus'" in err for err in errors)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtils:
    def test_generate_id_format(self) -> None:
        gid = generate_id()
        assert len(gid) == 36  # UUID4 string length
        assert gid.count("-") == 4

    def test_generate_id_unique(self) -> None:
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100

    def test_normalize_text(self) -> None:
        assert normalize_text("  Hello   World  ") == "hello world"

    def test_normalize_text_empty(self) -> None:
        assert normalize_text("") == ""
