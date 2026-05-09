"""Tests for the production graph context expander bridge."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from graph.models import GraphMetrics, SubgraphResult
from graph.service_models import GraphBuildReceipt, GraphBuildTask
from rag.adapters.graph_bridge import ServiceGraphContextExpander
from rag.adapters.protocols import GraphContextExpanderProtocol
from rag.models import RetrievedContextItem
from shared.types import Entity, Relationship


def _make_entity(entity_id: str, entity_type: str = "claim") -> Entity:
    return Entity(
        id=entity_id,
        type=entity_type,
        properties={},
        metadata={},
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )


def _make_relationship(
    relationship_id: str,
    *,
    relationship_type: str,
    source_id: str,
    target_id: str,
) -> Relationship:
    return Relationship(
        id=relationship_id,
        type=relationship_type,
        source_id=source_id,
        target_id=target_id,
        properties={},
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )


def _item(
    *,
    record_id: str,
    content_id: str,
    entity_id: str | None,
    score: float = 0.5,
    extra_key: str | None = None,
) -> RetrievedContextItem:
    metadata: dict[str, str | int | float | bool] = {}
    if entity_id is not None:
        key = extra_key or "entity_id"
        metadata[key] = entity_id
    return RetrievedContextItem(
        record_id=record_id,
        content_id=content_id,
        score=score,
        content="snippet content",
        metadata=metadata,
    )


class _RecordingGraphService:
    """In-memory fake conforming to `GraphServiceProtocol`."""

    def __init__(self, results: dict[str, SubgraphResult]) -> None:
        self._results = results
        self.calls: list[tuple[str, str, int]] = []

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt:  # pragma: no cover
        del task
        raise NotImplementedError

    def get_entity(self, knowledge_base_id: str, entity_id: str) -> Entity | None:  # pragma: no cover
        del knowledge_base_id, entity_id
        return None

    def query_neighborhood(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
    ) -> SubgraphResult:
        self.calls.append((knowledge_base_id, entity_id, depth))
        return self._results.get(entity_id, SubgraphResult())

    def search_entities(  # pragma: no cover
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        del knowledge_base_id, query, limit, offset
        return []

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics:  # pragma: no cover
        del knowledge_base_id
        return GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)


def test_service_graph_context_expander_satisfies_protocol() -> None:
    service = _RecordingGraphService({})

    expander: GraphContextExpanderProtocol = ServiceGraphContextExpander(service)

    assert isinstance(expander, GraphContextExpanderProtocol)


def test_service_graph_context_expander_traverses_each_entity() -> None:
    service = _RecordingGraphService(
        {
            "ent-1": SubgraphResult(
                entities=[_make_entity("ent-1"), _make_entity("ent-1-neighbor")],
                relationships=[
                    _make_relationship(
                        "rel-1",
                        relationship_type="references",
                        source_id="ent-1",
                        target_id="ent-1-neighbor",
                    )
                ],
            ),
            "ent-2": SubgraphResult(
                entities=[_make_entity("ent-2"), _make_entity("ent-2-neighbor")],
                relationships=[
                    _make_relationship(
                        "rel-2",
                        relationship_type="similar_to",
                        source_id="ent-2",
                        target_id="ent-2-neighbor",
                    )
                ],
            ),
        }
    )
    expander = ServiceGraphContextExpander(service, depth=2)

    context = expander.expand(
        knowledge_base_id="kb-42",
        context_items=[
            _item(record_id="r-1", content_id="c-1", entity_id="ent-1"),
            _item(record_id="r-2", content_id="c-2", entity_id="ent-2"),
        ],
    )

    assert {(call[0], call[1], call[2]) for call in service.calls} == {
        ("kb-42", "ent-1", 2),
        ("kb-42", "ent-2", 2),
    }
    assert {node.entity_id for node in context.nodes} == {
        "ent-1",
        "ent-1-neighbor",
        "ent-2",
        "ent-2-neighbor",
    }
    assert {edge.relationship_id for edge in context.edges} == {"rel-1", "rel-2"}
    assert context.summary is not None
    assert "4 graph nodes" in context.summary
    assert "2 relationships" in context.summary


def test_service_graph_context_expander_default_depth_is_one() -> None:
    service = _RecordingGraphService(
        {"ent-1": SubgraphResult(entities=[_make_entity("ent-1")], relationships=[])}
    )
    expander = ServiceGraphContextExpander(service)

    expander.expand(
        knowledge_base_id="kb-1",
        context_items=[_item(record_id="r-1", content_id="c-1", entity_id="ent-1")],
    )

    assert service.calls == [("kb-1", "ent-1", 1)]


def test_service_graph_context_expander_returns_empty_when_no_entity_metadata() -> None:
    service = _RecordingGraphService({})
    expander = ServiceGraphContextExpander(service)

    context = expander.expand(
        knowledge_base_id="kb-1",
        context_items=[_item(record_id="r-1", content_id="c-1", entity_id=None)],
    )

    assert context.nodes == []
    assert context.edges == []
    assert context.summary == ""
    assert service.calls == []


def test_service_graph_context_expander_returns_empty_summary_when_no_neighbors() -> None:
    service = _RecordingGraphService({"ent-1": SubgraphResult()})
    expander = ServiceGraphContextExpander(service)

    context = expander.expand(
        knowledge_base_id="kb-1",
        context_items=[_item(record_id="r-1", content_id="c-1", entity_id="ent-1")],
    )

    assert context.nodes == []
    assert context.edges == []
    assert context.summary == ""
    assert service.calls == [("kb-1", "ent-1", 1)]


def test_service_graph_context_expander_deduplicates_repeated_entity_ids() -> None:
    service = _RecordingGraphService(
        {"ent-1": SubgraphResult(entities=[_make_entity("ent-1")], relationships=[])}
    )
    expander = ServiceGraphContextExpander(service)

    context = expander.expand(
        knowledge_base_id="kb-1",
        context_items=[
            _item(record_id="r-1", content_id="c-1", entity_id="ent-1"),
            _item(record_id="r-2", content_id="c-2", entity_id="ent-1"),
        ],
    )

    assert service.calls == [("kb-1", "ent-1", 1)]
    assert [node.entity_id for node in context.nodes] == ["ent-1"]


def test_service_graph_context_expander_recognizes_camelcase_entity_id_key() -> None:
    service = _RecordingGraphService(
        {"ent-9": SubgraphResult(entities=[_make_entity("ent-9")], relationships=[])}
    )
    expander = ServiceGraphContextExpander(service)

    context = expander.expand(
        knowledge_base_id="kb-1",
        context_items=[
            _item(
                record_id="r-1",
                content_id="c-1",
                entity_id="ent-9",
                extra_key="entityId",
            )
        ],
    )

    assert service.calls == [("kb-1", "ent-9", 1)]
    assert [node.entity_id for node in context.nodes] == ["ent-9"]


def test_service_graph_context_expander_skips_items_with_blank_entity_id() -> None:
    service = _RecordingGraphService({})
    expander = ServiceGraphContextExpander(service)

    context = expander.expand(
        knowledge_base_id="kb-1",
        context_items=[
            RetrievedContextItem(
                record_id="r-1",
                content_id="c-1",
                score=0.5,
                content="snippet",
                metadata={"entity_id": "   "},
            ),
        ],
    )

    assert context.nodes == []
    assert service.calls == []


def test_service_graph_context_expander_rejects_negative_depth() -> None:
    service = _RecordingGraphService({})

    with pytest.raises(ValueError):
        ServiceGraphContextExpander(service, depth=-1)


def test_service_graph_context_expander_deduplicates_nodes_and_edges_across_subgraphs() -> None:
    """Same entity / relationship returned for two different seed entities should
    be added only once to the resulting GraphContext."""

    shared_entity = _make_entity("shared", entity_type="claim")
    shared_relationship = _make_relationship(
        "rel-shared",
        relationship_type="references",
        source_id="ent-1",
        target_id="shared",
    )
    service = _RecordingGraphService(
        {
            "ent-1": SubgraphResult(
                entities=[_make_entity("ent-1"), shared_entity],
                relationships=[shared_relationship],
            ),
            "ent-2": SubgraphResult(
                entities=[_make_entity("ent-2"), shared_entity],
                relationships=[shared_relationship],
            ),
        }
    )
    expander = ServiceGraphContextExpander(service)

    context = expander.expand(
        knowledge_base_id="kb-1",
        context_items=[
            _item(record_id="r-1", content_id="c-1", entity_id="ent-1"),
            _item(record_id="r-2", content_id="c-2", entity_id="ent-2"),
        ],
    )

    node_ids = [node.entity_id for node in context.nodes]
    assert node_ids.count("shared") == 1
    edge_ids = [edge.relationship_id for edge in context.edges]
    assert edge_ids.count("rel-shared") == 1
