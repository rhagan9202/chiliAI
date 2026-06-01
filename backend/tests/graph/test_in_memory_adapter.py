"""Tests for the in-memory graph adapter."""

from __future__ import annotations

import pytest

from graph.adapters.in_memory import InMemoryGraphRepository
from shared.types import Entity, Relationship


def test_in_memory_graph_repository_stores_entities_and_relationships() -> None:
    repository = InMemoryGraphRepository()

    repository.upsert_entities(
        "kb-1",
        [Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="relationship-1",
                type="submitted_by",
                source_id="entity-1",
                target_id="entity-2",
            )
        ],
    )

    assert [entity.id for entity in repository.get_entities("kb-1")] == ["entity-1"]
    assert [relationship.id for relationship in repository.get_relationships("kb-1")] == [
        "relationship-1"
    ]


@pytest.fixture()
def populated_repository() -> InMemoryGraphRepository:
    repository = InMemoryGraphRepository()

    repository.upsert_entities(
        "kb-1",
        [
            Entity(
                id="entity-1",
                type="claim",
                properties={"claim_id": "42", "description": "Unusual cardiac billing"},
            ),
            Entity(
                id="entity-2",
                type="provider",
                properties={"npi": "1234567890", "name": "Alice Clinic"},
            ),
            Entity(
                id="entity-3",
                type="provider",
                properties={"npi": "5555555555", "name": "Bob Partners"},
            ),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="relationship-1",
                type="submitted_by",
                source_id="entity-1",
                target_id="entity-2",
            ),
            Relationship(
                id="relationship-2",
                type="referred_to",
                source_id="entity-2",
                target_id="entity-3",
            ),
        ],
    )

    return repository


def test_get_entity_and_counts(populated_repository: InMemoryGraphRepository) -> None:
    assert populated_repository.get_entity(["kb-1"], "entity-2") is not None
    assert populated_repository.get_entity(["kb-1"], "missing") is None
    assert populated_repository.count_entities("kb-1") == 3
    assert populated_repository.count_relationships("kb-1") == 2


def test_counts_return_zero_for_empty_graph() -> None:
    repository = InMemoryGraphRepository()

    assert repository.count_entities("kb-1") == 0
    assert repository.count_relationships("kb-1") == 0


def test_get_entities_by_type_applies_pagination(populated_repository: InMemoryGraphRepository) -> None:
    assert [
        entity.id
        for entity in populated_repository.get_entities_by_type(
            "kb-1", "provider", limit=1, offset=0
        )
    ] == ["entity-2"]
    assert [
        entity.id
        for entity in populated_repository.get_entities_by_type(
            "kb-1", "provider", limit=10, offset=1
        )
    ] == ["entity-3"]
    assert populated_repository.get_entities_by_type("kb-1", "facility", limit=10, offset=0) == []


def test_get_entities_by_type_returns_empty_for_non_positive_limit_or_negative_offset(
    populated_repository: InMemoryGraphRepository,
) -> None:
    assert populated_repository.get_entities_by_type(
        "kb-1", "provider", limit=0, offset=0
    ) == []
    assert populated_repository.get_entities_by_type(
        "kb-1", "provider", limit=-1, offset=0
    ) == []
    assert populated_repository.get_entities_by_type(
        "kb-1", "provider", limit=10, offset=-1
    ) == []


def test_search_entities_matches_string_properties_case_insensitively(
    populated_repository: InMemoryGraphRepository,
) -> None:
    assert [
        entity.id
        for entity in populated_repository.search_entities(["kb-1"], "ALICE", limit=10)
    ] == ["entity-2"]
    assert [
        entity.id
        for entity in populated_repository.search_entities(["kb-1"], "cardiac", limit=10)
    ] == ["entity-1"]


def test_search_entities_ignores_non_string_properties_and_blank_queries() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="entity-1", type="claim", properties={"amount": 125, "claim_id": "42"}),
        ],
    )

    assert repository.search_entities(["kb-1"], "125", limit=10) == []
    assert repository.search_entities(["kb-1"], "   ", limit=10) == []


def test_search_entities_returns_empty_for_non_positive_limit(
    populated_repository: InMemoryGraphRepository,
) -> None:
    assert populated_repository.search_entities(["kb-1"], "alice", limit=0) == []
    assert populated_repository.search_entities(["kb-1"], "alice", limit=-1) == []


def test_get_neighbors_traverses_outbound_bfs(populated_repository: InMemoryGraphRepository) -> None:
    neighbors = populated_repository.get_neighbors("kb-1", "entity-1", depth=2, direction="out")

    assert {entity.id for entity in neighbors.entities} == {"entity-1", "entity-2", "entity-3"}
    assert {relationship.id for relationship in neighbors.relationships} == {"relationship-1", "relationship-2"}


def test_get_neighbors_respects_inbound_direction(populated_repository: InMemoryGraphRepository) -> None:
    neighbors = populated_repository.get_neighbors("kb-1", "entity-3", depth=2, direction="in")

    assert {entity.id for entity in neighbors.entities} == {"entity-1", "entity-2", "entity-3"}
    assert {relationship.id for relationship in neighbors.relationships} == {"relationship-1", "relationship-2"}


def test_get_neighbors_with_depth_zero_returns_only_root_entity(
    populated_repository: InMemoryGraphRepository,
) -> None:
    neighbors = populated_repository.get_neighbors("kb-1", "entity-1", depth=0, direction="both")

    assert [entity.id for entity in neighbors.entities] == ["entity-1"]
    assert neighbors.relationships == []


def test_get_neighbors_returns_empty_for_missing_entity() -> None:
    repository = InMemoryGraphRepository()

    neighbors = repository.get_neighbors("kb-1", "missing", depth=1, direction="both")

    assert neighbors.entities == []
    assert neighbors.relationships == []


def test_get_neighbors_rejects_invalid_direction(
    populated_repository: InMemoryGraphRepository,
) -> None:
    with pytest.raises(ValueError, match="direction must be one of"):
        populated_repository.get_neighbors(
            "kb-1",
            "entity-1",
            depth=1,
            direction="sideways",  # type: ignore[arg-type]
        )


def test_get_neighbors_uses_rebuilt_adjacency_after_mutation(
    populated_repository: InMemoryGraphRepository,
) -> None:
    first_neighbors = populated_repository.get_neighbors("kb-1", "entity-1", depth=1, direction="out")
    assert {relationship.id for relationship in first_neighbors.relationships} == {"relationship-1"}

    populated_repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="relationship-3",
                type="escalated_to",
                source_id="entity-1",
                target_id="entity-3",
            )
        ],
    )

    second_neighbors = populated_repository.get_neighbors("kb-1", "entity-1", depth=1, direction="out")
    assert {relationship.id for relationship in second_neighbors.relationships} == {
        "relationship-1",
        "relationship-3",
    }


def test_get_subgraph_unions_multiple_seed_neighborhoods(
    populated_repository: InMemoryGraphRepository,
) -> None:
    result = populated_repository.get_subgraph("kb-1", ["entity-1", "entity-3"], depth=1)

    assert {entity.id for entity in result.entities} == {"entity-1", "entity-2", "entity-3"}
    relationship_ids = [relationship.id for relationship in result.relationships]
    assert set(relationship_ids) == {"relationship-1", "relationship-2"}
    # entity-2 is reachable from both seeds; relationships must be deduplicated.
    assert len(relationship_ids) == len(set(relationship_ids))


def test_get_subgraph_empty_seeds_returns_empty(
    populated_repository: InMemoryGraphRepository,
) -> None:
    result = populated_repository.get_subgraph("kb-1", [], depth=2)

    assert result.entities == []
    assert result.relationships == []


def test_get_subgraph_skips_unknown_seed(
    populated_repository: InMemoryGraphRepository,
) -> None:
    result = populated_repository.get_subgraph("kb-1", ["entity-1", "missing"], depth=1)

    assert {entity.id for entity in result.entities} == {"entity-1", "entity-2"}
    assert {relationship.id for relationship in result.relationships} == {"relationship-1"}


def test_get_subgraph_is_kb_scoped(
    populated_repository: InMemoryGraphRepository,
) -> None:
    result = populated_repository.get_subgraph("kb-2", ["entity-1"], depth=3)

    assert result.entities == []
    assert result.relationships == []


def test_delete_relationship_is_idempotent(populated_repository: InMemoryGraphRepository) -> None:
    populated_repository.delete_relationship("kb-1", "relationship-2")
    populated_repository.delete_relationship("kb-1", "relationship-2")

    assert populated_repository.count_relationships("kb-1") == 1


def test_delete_entity_cascades_relationship_cleanup(
    populated_repository: InMemoryGraphRepository,
) -> None:
    populated_repository.delete_entity("kb-1", "entity-2")

    assert populated_repository.get_entity(["kb-1"], "entity-2") is None
    assert populated_repository.count_entities("kb-1") == 2
    assert populated_repository.count_relationships("kb-1") == 0


def test_delete_entity_is_idempotent() -> None:
    repository = InMemoryGraphRepository()

    repository.delete_entity("kb-1", "missing")

    assert repository.count_entities("kb-1") == 0
    assert repository.count_relationships("kb-1") == 0


def test_delete_knowledge_base_clears_only_target_namespace() -> None:
    repository = InMemoryGraphRepository()
    for knowledge_base_id in ["kb-1", "kb-2"]:
        repository.upsert_entities(
            knowledge_base_id,
            [
                Entity(id="entity-1", type="claim", properties={}),
                Entity(id="entity-2", type="provider", properties={}),
            ],
        )
        repository.upsert_relationships(
            knowledge_base_id,
            [
                Relationship(
                    id="relationship-1",
                    type="submitted_by",
                    source_id="entity-1",
                    target_id="entity-2",
                )
            ],
        )
        assert repository.get_neighbors(
            knowledge_base_id,
            "entity-1",
            depth=1,
            direction="out",
        ).relationships

    repository.delete_knowledge_base("kb-1")
    repository.delete_knowledge_base("kb-1")

    assert repository.count_entities("kb-1") == 0
    assert repository.count_relationships("kb-1") == 0
    assert repository.get_neighbors("kb-1", "entity-1", depth=1, direction="out").entities == []
    assert repository.count_entities("kb-2") == 2
    assert repository.count_relationships("kb-2") == 1


def test_in_memory_graph_repository_transaction_commits_changes() -> None:
    repository = InMemoryGraphRepository()

    with repository.transaction("kb-1"):
        repository.upsert_entities(
            "kb-1",
            [Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
        )
        repository.upsert_relationships(
            "kb-1",
            [
                Relationship(
                    id="relationship-1",
                    type="submitted_by",
                    source_id="entity-1",
                    target_id="entity-2",
                )
            ],
        )

    assert repository.count_entities("kb-1") == 1
    assert repository.count_relationships("kb-1") == 1


def test_in_memory_graph_repository_transaction_rolls_back_changes() -> None:
    repository = InMemoryGraphRepository()

    with pytest.raises(RuntimeError, match="boom"):
        with repository.transaction("kb-1"):
            repository.upsert_entities(
                "kb-1",
                [Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
            )
            repository.upsert_relationships(
                "kb-1",
                [
                    Relationship(
                        id="relationship-1",
                        type="submitted_by",
                        source_id="entity-1",
                        target_id="entity-2",
                    )
                ],
            )
            raise RuntimeError("boom")

    assert repository.count_entities("kb-1") == 0
    assert repository.count_relationships("kb-1") == 0

def test_in_memory_repository_update_entity_properties_is_idempotent() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [Entity(id="provider-1", type="claim", properties={"name": "Provider A"})],
    )

    first = repository.update_entity_properties(
        "kb-1",
        "provider-1",
        {"risk_score": 0.7, "risk_level": "high"},
    )
    second = repository.update_entity_properties(
        "kb-1",
        "provider-1",
        {"risk_score": 0.7, "risk_level": "high"},
    )

    assert first.properties["risk_score"] == 0.7
    assert first.properties["risk_level"] == "high"
    assert first.properties["name"] == "Provider A"
    assert second.properties == first.properties


def test_in_memory_repository_update_entity_properties_merges_with_existing() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [Entity(id="provider-1", type="claim", properties={"name": "Provider A"})],
    )

    repository.update_entity_properties(
        "kb-1",
        "provider-1",
        {"risk_score": 0.5},
    )
    updated = repository.update_entity_properties(
        "kb-1",
        "provider-1",
        {"risk_level": "medium"},
    )

    assert updated.properties["name"] == "Provider A"
    assert updated.properties["risk_score"] == 0.5
    assert updated.properties["risk_level"] == "medium"


def test_in_memory_repository_update_entity_properties_raises_when_missing() -> None:
    repository = InMemoryGraphRepository()
    with pytest.raises(KeyError):
        repository.update_entity_properties(
            "kb-1", "missing-entity", {"risk_score": 0.1}
        )


def test_in_memory_get_entity_finds_entity_across_multiple_kb_ids() -> None:
    """get_entity with a multi-KB scope returns the match from whichever KB has it."""
    repo = InMemoryGraphRepository()
    entity = Entity(id="entity-1", type="claim", properties={"x": 1})
    with repo.transaction("kb-claims"):
        repo.upsert_entities("kb-claims", [entity])

    result = repo.get_entity(["kb-other-empty", "kb-claims"], "entity-1")

    assert result is not None
    assert result.id == "entity-1"


def test_in_memory_get_entity_returns_none_when_no_kb_in_scope_has_it() -> None:
    repo = InMemoryGraphRepository()
    result = repo.get_entity(["kb-a", "kb-b"], "entity-missing")
    assert result is None


def test_in_memory_search_entities_spans_all_knowledge_bases() -> None:
    """search_entities iterates every KB even when the first has matches."""
    repo = InMemoryGraphRepository()

    # Three matches in KB-a, two in KB-b. Search "alpha" with limit large enough for all.
    repo.upsert_entities("kb-a", [
        Entity(id="a-1", type="claim", properties={"name": "Alpha 1"}),
        Entity(id="a-2", type="claim", properties={"name": "Alpha 2"}),
        Entity(id="a-3", type="claim", properties={"name": "Alpha 3"}),
    ])
    repo.upsert_entities("kb-b", [
        Entity(id="b-1", type="claim", properties={"name": "Alpha 4"}),
        Entity(id="b-2", type="claim", properties={"name": "Alpha 5"}),
    ])

    results = repo.search_entities(["kb-a", "kb-b"], "alpha", limit=10)
    result_ids = {entity.id for entity in results}

    assert result_ids == {"a-1", "a-2", "a-3", "b-1", "b-2"}


def test_in_memory_search_entities_limit_applies_across_combined_kb_results() -> None:
    """The limit applies to the combined cross-KB result set, not per-KB."""
    repo = InMemoryGraphRepository()

    # KB-a alone has more matches than limit. KB-b also has matches.
    repo.upsert_entities("kb-a", [
        Entity(id=f"a-{i}", type="claim", properties={"name": f"Match {i}"})
        for i in range(1, 7)  # 6 matches
    ])
    repo.upsert_entities("kb-b", [
        Entity(id=f"b-{i}", type="claim", properties={"name": f"Match B{i}"})
        for i in range(1, 4)  # 3 matches
    ])

    results = repo.search_entities(["kb-a", "kb-b"], "match", limit=4)

    # Exactly limit=4 entities returned, drawn from the combined scope.
    assert len(results) == 4
