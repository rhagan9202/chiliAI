"""Verify Relationship carries an opaque metadata dict for provenance."""

from __future__ import annotations

from shared.types import Relationship


def test_relationship_has_default_empty_metadata() -> None:
    relationship = Relationship(
        id="rel-1",
        type="submitted_by",
        source_id="claim:A",
        target_id="provider:B",
    )
    assert relationship.metadata == {}


def test_relationship_accepts_metadata() -> None:
    relationship = Relationship(
        id="rel-1",
        type="submitted_by",
        source_id="claim:A",
        target_id="provider:B",
        metadata={"source_kind": "record", "source_feed": "carrier_claims_a"},
    )
    assert relationship.metadata["source_kind"] == "record"
    assert relationship.metadata["source_feed"] == "carrier_claims_a"
