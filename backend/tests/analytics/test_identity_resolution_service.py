"""Tests for SAFE-CMS-012 identity resolution candidate scoring."""

from __future__ import annotations

from analytics.identity_resolution import (
    IdentityCandidateEntity,
    IdentityRelationshipProjectionRequest,
    IdentityResolutionRequest,
    IdentityResolutionService,
)
from shared.types import Entity


def _entity(entity_id: str, **properties: object) -> Entity:
    return Entity(id=entity_id, type="provider", properties=properties)


def test_identity_resolution_scores_candidates_with_auditable_reasons() -> None:
    service = IdentityResolutionService()
    request = IdentityResolutionRequest(
        knowledge_base_id="kb1",
        source_entity=_entity(
            "source:1",
            source_provider_id="SRC-001",
            npi="123-45-6789",
            address="10 Main St, Nashville TN",
        ),
        candidates=[
            IdentityCandidateEntity(
                knowledge_base_id="kb1",
                entity=_entity(
                    "canonical:strong",
                    source_provider_id="SRC-001",
                    npi="123456789",
                    address="10 main street nashville tn",
                ),
            ),
            IdentityCandidateEntity(
                knowledge_base_id="kb1",
                entity=_entity(
                    "canonical:weak",
                    source_provider_id="SRC-999",
                    npi="999999999",
                    address="10 Main St, Nashville TN",
                ),
            ),
        ],
        natural_key_fields=["source_provider_id"],
        identifier_fields=["npi"],
        address_fields=["address"],
    )

    result = service.score_candidates(request)

    assert result.knowledge_base_id == "kb1"
    assert result.source_entity_id == "source:1"
    assert [candidate.entity_id for candidate in result.candidates] == [
        "canonical:strong",
        "canonical:weak",
    ]
    assert result.candidates[0].confidence == "high"
    assert result.candidates[0].score > result.candidates[1].score
    assert result.candidates[0].review_state == "auto_linkable"
    assert {
        (reason.field, reason.reason)
        for reason in result.candidates[0].match_reasons
    } == {
        ("source_provider_id", "natural_key_match"),
        ("npi", "identifier_match"),
        ("address", "address_match"),
    }
    assert result.candidates[1].confidence == "low"
    assert result.candidates[1].review_state == "needs_review"


def test_identity_resolution_excludes_candidates_outside_request_kb() -> None:
    service = IdentityResolutionService()
    request = IdentityResolutionRequest(
        knowledge_base_id="kb1",
        source_entity=_entity("source:1", natural_id="A-1"),
        candidates=[
            IdentityCandidateEntity(
                knowledge_base_id="kb2",
                entity=_entity("canonical:other-kb", natural_id="A-1"),
            ),
            IdentityCandidateEntity(
                knowledge_base_id="kb1",
                entity=_entity("canonical:same-kb", natural_id="A-1"),
            ),
        ],
        natural_key_fields=["natural_id"],
    )

    result = service.score_candidates(request)

    assert [candidate.entity_id for candidate in result.candidates] == [
        "canonical:same-kb"
    ]
    assert result.excluded_candidate_ids == ["canonical:other-kb"]


def test_identity_resolution_projects_graph_relationships_with_confidence_metadata() -> None:
    service = IdentityResolutionService()
    source_entity = _entity(
        "source:1",
        source_provider_id="SRC-001",
        npi="123-45-6789",
    )
    result = service.score_candidates(
        IdentityResolutionRequest(
            knowledge_base_id="kb1",
            source_entity=source_entity,
            candidates=[
                IdentityCandidateEntity(
                    knowledge_base_id="kb1",
                    entity=_entity(
                        "canonical:strong",
                        source_provider_id="SRC-001",
                        npi="123456789",
                    ),
                )
            ],
            natural_key_fields=["source_provider_id"],
            identifier_fields=["npi"],
        )
    )

    relationships = service.project_identity_relationships(
        IdentityRelationshipProjectionRequest(
            knowledge_base_id="kb1",
            source_entity=source_entity,
            candidates=result.candidates,
            relationship_type="resolved_identity",
            decision_source="identity_resolution.candidate_scoring",
            source_refs=["source-system:a"],
        )
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.id == "identity_link:kb1:canonical-strong:source-1"
    assert relationship.type == "resolved_identity"
    assert relationship.source_id == "canonical:strong"
    assert relationship.target_id == "source:1"
    assert relationship.weight == result.candidates[0].score
    assert relationship.properties == {
        "confidence": "high",
        "score": 0.85,
        "review_state": "auto_linkable",
        "decision_source": "identity_resolution.candidate_scoring",
    }
    assert relationship.metadata["knowledge_base_id"] == "kb1"
    assert relationship.metadata["source_entity_type"] == "provider"
    assert relationship.metadata["candidate_entity_type"] == "provider"
    assert relationship.metadata["source_refs"] == ["source-system:a"]
    assert relationship.metadata["match_reasons"] == [
        {
            "field": "source_provider_id",
            "reason": "natural_key_match",
            "score_contribution": 0.55,
        },
        {
            "field": "npi",
            "reason": "identifier_match",
            "score_contribution": 0.3,
        },
    ]
