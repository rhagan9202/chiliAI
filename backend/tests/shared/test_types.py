"""Tests for the shared types module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pytest
from pydantic import ValidationError

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
    validate_relationship,
)
from shared.utils import generate_id, normalize_text, utc_now


type KnowledgeBaseStatus = Literal[
    "active", "building", "ready", "error", "archived"
]
type AlertStatus = Literal[
    "open", "acknowledged", "investigating", "resolved", "dismissed"
]


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
        assert e.created_at.tzinfo == timezone.utc
        assert e.updated_at is None
        assert e.version == 1

    def test_construct_full(self) -> None:
        now = utc_now()
        e = Entity(
            id="e2",
            type="claim",
            properties={"amount": 150.00},
            metadata={"source": "csv"},
            created_at=now,
            updated_at=now,
            version=3,
        )
        assert e.properties["amount"] == 150.00
        assert e.created_at == now
        assert e.updated_at == now
        assert e.version == 3


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
        assert r.created_at.tzinfo == timezone.utc
        assert r.updated_at is None
        assert r.version == 1
        assert r.weight is None

    def test_construct_with_audit_and_weight_fields(self) -> None:
        now = utc_now()
        r = Relationship(
            id="r2",
            type="billed_for",
            source_id="claim2",
            target_id="beneficiary1",
            properties={"confidence": 0.98},
            created_at=now,
            updated_at=now,
            version=4,
            weight=0.75,
        )

        assert r.created_at == now
        assert r.updated_at == now
        assert r.version == 4
        assert r.weight == 0.75


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
        assert a.status == "open"
        assert a.updated_at is None
        assert a.resolved_by is None
        assert a.resolution_notes is None

    @pytest.mark.parametrize(
        ("status",),
        [
            ("open",),
            ("acknowledged",),
            ("investigating",),
            ("resolved",),
            ("dismissed",),
        ],
    )
    def test_accepts_supported_status_values(self, status: AlertStatus) -> None:
        now = datetime.now(tz=timezone.utc)

        alert = Alert(
            id="a1",
            entity_type="provider",
            entity_id="p1",
            severity="high",
            title="Anomalous billing",
            reasoning="Billing volume exceeded threshold.",
            created_at=now,
            status=status,
            updated_at=now,
            resolved_by="analyst-1",
            resolution_notes="Reviewed and closed.",
        )

        assert alert.status == status
        assert alert.updated_at == now
        assert alert.resolved_by == "analyst-1"
        assert alert.resolution_notes == "Reviewed and closed."

    def test_rejects_unsupported_status_value(self) -> None:
        now = datetime.now(tz=timezone.utc)

        with pytest.raises(ValidationError):
            Alert.model_validate(
                {
                    "id": "a1",
                    "entity_type": "provider",
                    "entity_id": "p1",
                    "severity": "high",
                    "title": "Anomalous billing",
                    "reasoning": "Billing volume exceeded threshold.",
                    "created_at": now,
                    "status": "pending",
                }
            )


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
        assert ep.created_at.tzinfo == timezone.utc
        assert ep.scores == {}
        assert ep.source_documents == []

    def test_construct_with_created_at_and_source_documents(self) -> None:
        now = utc_now()

        ep = EvidencePack(
            id="ep1",
            alert_id="a1",
            reasoning="Cluster analysis",
            subgraph_nodes=["n1", "n2"],
            subgraph_edges=["e1"],
            confidence=0.92,
            created_at=now,
            source_documents=["doc-1", "doc-2"],
        )

        assert ep.created_at == now
        assert ep.source_documents == ["doc-1", "doc-2"]


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
        assert kb.updated_at is None

    @pytest.mark.parametrize(
        ("status",),
        [
            ("active",),
            ("building",),
            ("ready",),
            ("error",),
            ("archived",),
        ],
    )
    def test_accepts_supported_status_values(self, status: KnowledgeBaseStatus) -> None:
        now = datetime.now(tz=timezone.utc)

        kb = KnowledgeBase(
            id="kb1",
            name="Medicare Policies",
            description="CMS policy docs",
            status=status,
            created_at=now,
            updated_at=now,
        )

        assert kb.status == status
        assert kb.updated_at == now

    def test_rejects_unsupported_status_value(self) -> None:
        now = datetime.now(tz=timezone.utc)

        with pytest.raises(ValidationError):
            KnowledgeBase.model_validate(
                {
                    "id": "kb1",
                    "name": "Medicare Policies",
                    "description": "CMS policy docs",
                    "status": "draft",
                    "created_at": now,
                }
            )


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

    def test_platform_owned_fields_are_skipped(self, entity_defs: list[EntityDefinition]) -> None:
        now = utc_now()
        e = Entity(
            id="1",
            type="provider",
            properties={
                "npi": "123",
                "created_at": now,
                "updated_at": now,
                "version": 2,
            },
        )

        assert validate_entity(e, entity_defs) == []

    def test_missing_required_property(self) -> None:
        entity_defs = [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                properties={
                    "npi": PropertyDefinition(
                        type=PropertyType.STRING,
                        display="NPI",
                        required=True,
                    ),
                },
            ),
        ]

        errors = validate_entity(Entity(id="1", type="provider"), entity_defs)

        assert errors == [
            "Missing required property 'npi' on entity type 'provider'."
        ]

    @pytest.mark.parametrize(
        ("definition", "value", "expected_fragment"),
        [
            (
                PropertyDefinition(
                    type=PropertyType.INTEGER,
                    display="Count",
                    min_value=1,
                ),
                0,
                "must be >= 1.0",
            ),
            (
                PropertyDefinition(
                    type=PropertyType.DECIMAL,
                    display="Amount",
                    max_value=100,
                ),
                101.5,
                "must be <= 100.0",
            ),
            (
                PropertyDefinition(
                    type=PropertyType.STRING,
                    display="Code",
                    min_length=3,
                ),
                "ab",
                "must have length >= 3",
            ),
            (
                PropertyDefinition(
                    type=PropertyType.STRING,
                    display="Code",
                    max_length=3,
                ),
                "abcd",
                "must have length <= 3",
            ),
            (
                PropertyDefinition(
                    type=PropertyType.STRING,
                    display="NPI",
                    pattern=r"\d{10}",
                ),
                "abc",
                "must match pattern",
            ),
            (
                PropertyDefinition(
                    type=PropertyType.ENUM,
                    display="Status",
                    enum_values=["active", "inactive"],
                ),
                "pending",
                "must be one of ['active', 'inactive']",
            ),
            (
                PropertyDefinition(type=PropertyType.DATE, display="Service Date"),
                "not-a-date",
                "must be of type 'date'",
            ),
            (
                PropertyDefinition(type=PropertyType.LIST, display="Tags"),
                "not-a-list",
                "must be of type 'list'",
            ),
            (
                PropertyDefinition(type=PropertyType.BOOLEAN, display="Flag"),
                "true",
                "must be of type 'boolean'",
            ),
            (
                PropertyDefinition(type=PropertyType.NESTED, display="Metadata"),
                [],
                "must be of type 'nested'",
            ),
        ],
    )
    def test_property_validation_errors(
        self,
        definition: PropertyDefinition,
        value: object,
        expected_fragment: str,
    ) -> None:
        entity_defs = [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                properties={"field": definition},
            ),
        ]

        errors = validate_entity(
            Entity(id="1", type="provider", properties={"field": value}),
            entity_defs,
        )

        assert len(errors) == 1
        assert expected_fragment in errors[0]

    def test_integer_validation_rejects_bool_values(self) -> None:
        entity_defs = [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                properties={
                    "count": PropertyDefinition(
                        type=PropertyType.INTEGER,
                        display="Count",
                    ),
                },
            ),
        ]

        errors = validate_entity(
            Entity(id="1", type="provider", properties={"count": True}),
            entity_defs,
        )

        assert errors == [
            "Property 'count' on entity type 'provider' must be of type 'integer'."
        ]

    def test_property_validation_accepts_supported_types(self) -> None:
        entity_defs = [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                properties={
                    "service_date": PropertyDefinition(
                        type=PropertyType.DATE,
                        display="Service Date",
                    ),
                    "tags": PropertyDefinition(type=PropertyType.LIST, display="Tags"),
                    "flag": PropertyDefinition(type=PropertyType.BOOLEAN, display="Flag"),
                    "metadata": PropertyDefinition(
                        type=PropertyType.NESTED,
                        display="Metadata",
                    ),
                },
            ),
        ]

        errors = validate_entity(
            Entity(
                id="1",
                type="provider",
                properties={
                    "service_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    "tags": ["a", "b"],
                    "flag": True,
                    "metadata": {"key": "value"},
                },
            ),
            entity_defs,
        )

        assert errors == []


class TestValidateRelationship:
    @pytest.fixture()
    def relationship_defs(self) -> list[RelationshipDefinition]:
        return [
            RelationshipDefinition(
                name="submitted_by",
                display_label="Submitted By",
                source="claim",
                target="provider",
            ),
        ]

    @pytest.fixture()
    def entities_by_id(self) -> dict[str, Entity]:
        return {
            "claim1": Entity(id="claim1", type="claim"),
            "provider1": Entity(id="provider1", type="provider"),
            "beneficiary1": Entity(id="beneficiary1", type="beneficiary"),
        }

    def test_valid_relationship(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="submitted_by",
            source_id="claim1",
            target_id="provider1",
        )

        assert validate_relationship(relationship, relationship_defs, entities_by_id) == []

    def test_unknown_relationship_type(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="unknown",
            source_id="claim1",
            target_id="provider1",
        )

        errors = validate_relationship(relationship, relationship_defs, entities_by_id)

        assert len(errors) == 1
        assert "Unknown relationship type" in errors[0]

    def test_missing_source_entity(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="submitted_by",
            source_id="missing",
            target_id="provider1",
        )

        errors = validate_relationship(relationship, relationship_defs, entities_by_id)

        assert errors == [
            "Relationship 'r1' source entity 'missing' was not validated."
        ]

    def test_wrong_source_type(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="submitted_by",
            source_id="beneficiary1",
            target_id="provider1",
        )

        errors = validate_relationship(relationship, relationship_defs, entities_by_id)

        assert errors == [
            "Relationship 'submitted_by' requires source type 'claim' but got 'beneficiary'."
        ]

    def test_missing_target_entity(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="submitted_by",
            source_id="claim1",
            target_id="missing",
        )

        errors = validate_relationship(relationship, relationship_defs, entities_by_id)

        assert errors == [
            "Relationship 'r1' target entity 'missing' was not validated."
        ]

    def test_wrong_target_type(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="submitted_by",
            source_id="claim1",
            target_id="beneficiary1",
        )

        errors = validate_relationship(relationship, relationship_defs, entities_by_id)

        assert errors == [
            "Relationship 'submitted_by' requires target type 'provider' but got 'beneficiary'."
        ]

    def test_unexpected_relationship_property(
        self,
        relationship_defs: list[RelationshipDefinition],
        entities_by_id: dict[str, Entity],
    ) -> None:
        relationship = Relationship(
            id="r1",
            type="submitted_by",
            source_id="claim1",
            target_id="provider1",
            properties={"bogus": "x"},
        )

        errors = validate_relationship(relationship, relationship_defs, entities_by_id)

        assert errors == [
            "Unexpected property 'bogus' on relationship type 'submitted_by'."
        ]


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
