"""Tests for config.schema — DomainConfig validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    ChunkingConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    IngestionSourceConfig,
)
from shared.types import (
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_entity(name: str = "thing") -> EntityDefinition:
    return EntityDefinition(
        name=name,
        display_label=name.title(),
        icon="box",
        properties={
            "id": PropertyDefinition(type=PropertyType.STRING, display="ID"),
        },
    )


def _make_config(
    *,
    entities: list[EntityDefinition] | None = None,
    relationships: list[RelationshipDefinition] | None = None,
) -> DomainConfig:
    """Build a minimal valid DomainConfig, optionally overriding parts."""
    ents = entities if entities is not None else [_minimal_entity("alpha")]
    rels = relationships if relationships is not None else []
    return DomainConfig(
        domain=DomainInfo(
            name="test", display_name="Test", description="Test domain"
        ),
        entities=ents,
        relationships=rels,
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(
            sources=[IngestionSourceConfig(type="file_upload", formats=["csv"])]
        ),
        alerts=AlertsConfig(thresholds={}),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestDomainConfigValid:
    def test_minimal_config(self) -> None:
        cfg = _make_config()
        assert cfg.domain.name == "test"
        assert len(cfg.entities) == 1

    def test_roundtrip(self) -> None:
        cfg = _make_config()
        data = cfg.model_dump()
        restored = DomainConfig.model_validate(data)
        assert restored == cfg

    def test_multiple_entities_and_relationships(self) -> None:
        ents = [_minimal_entity("a"), _minimal_entity("b")]
        rels = [
            RelationshipDefinition(
                name="a_to_b", display_label="A→B", source="a", target="b"
            )
        ]
        cfg = _make_config(entities=ents, relationships=rels)
        assert len(cfg.relationships) == 1

    def test_ingestion_chunking_defaults(self) -> None:
        cfg = _make_config()
        assert cfg.ingestion.chunking.strategy == "recursive"
        assert cfg.ingestion.chunking.chunk_size == 1000
        assert cfg.ingestion.chunking.chunk_overlap == 200

    def test_self_referencing_relationship(self) -> None:
        ents = [_minimal_entity("node")]
        rels = [
            RelationshipDefinition(
                name="links_to", display_label="Links To", source="node", target="node"
            )
        ]
        cfg = _make_config(entities=ents, relationships=rels)
        assert cfg.relationships[0].source == "node"


# ---------------------------------------------------------------------------
# Cross-field validation failures
# ---------------------------------------------------------------------------


class TestDomainConfigValidation:
    def test_duplicate_entity_names(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate entity name"):
            _make_config(entities=[_minimal_entity("x"), _minimal_entity("x")])

    def test_duplicate_relationship_names(self) -> None:
        ents = [_minimal_entity("a"), _minimal_entity("b")]
        dup_rel = RelationshipDefinition(
            name="link", display_label="Link", source="a", target="b"
        )
        with pytest.raises(ValidationError, match="Duplicate relationship name"):
            _make_config(entities=ents, relationships=[dup_rel, dup_rel])

    def test_relationship_bad_source(self) -> None:
        ents = [_minimal_entity("a")]
        rels = [
            RelationshipDefinition(
                name="r", display_label="R", source="missing", target="a"
            )
        ]
        with pytest.raises(ValidationError, match="source 'missing'"):
            _make_config(entities=ents, relationships=rels)

    def test_relationship_bad_target(self) -> None:
        ents = [_minimal_entity("a")]
        rels = [
            RelationshipDefinition(
                name="r", display_label="R", source="a", target="missing"
            )
        ]
        with pytest.raises(ValidationError, match="target 'missing'"):
            _make_config(entities=ents, relationships=rels)

    def test_enum_property_without_values(self) -> None:
        bad_entity = EntityDefinition(
            name="bad",
            display_label="Bad",
            icon="x",
            properties={
                "status": PropertyDefinition(
                    type=PropertyType.ENUM, display="Status"
                ),
            },
        )
        with pytest.raises(ValidationError, match="enum_values"):
            _make_config(entities=[bad_entity])

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            DomainConfig.model_validate({"domain": {"name": "x"}})


class TestChunkingConfig:
    def test_default_min_chunk_size_is_capped_for_small_chunk_sizes(self) -> None:
        config = ChunkingConfig(chunk_size=24, chunk_overlap=4)

        assert config.min_chunk_size == 24

    def test_chunk_overlap_must_be_smaller_than_chunk_size(self) -> None:
        with pytest.raises(ValidationError, match="chunk_overlap"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)

    def test_min_chunk_size_must_not_exceed_chunk_size(self) -> None:
        with pytest.raises(ValidationError, match="min_chunk_size"):
            ChunkingConfig(chunk_size=100, min_chunk_size=101)


# ---------------------------------------------------------------------------
# Each PropertyType value
# ---------------------------------------------------------------------------


class TestPropertyTypeValues:
    @pytest.mark.parametrize(
        "ptype",
        [pt for pt in PropertyType],
        ids=[pt.value for pt in PropertyType],
    )
    def test_each_property_type_in_entity(self, ptype: PropertyType) -> None:
        extra = {}
        if ptype is PropertyType.ENUM:
            extra["enum_values"] = ["a", "b"]
        prop = PropertyDefinition(type=ptype, display="Test", **extra)
        entity = EntityDefinition(
            name="test_entity",
            display_label="Test",
            icon="box",
            properties={"field": prop},
        )
        cfg = _make_config(entities=[entity])
        assert cfg.entities[0].properties["field"].type is ptype
