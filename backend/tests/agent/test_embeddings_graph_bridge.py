"""Tests for the agent graph-to-embeddings bridge."""

from __future__ import annotations

from analytics.gnn.service_models import (
    GnnAnalysisRequest,
    GnnAnalysisResponse,
)
from agent.embeddings_graph_bridge import GnnGraphEmbeddingProvider


class _RecordingGnnService:
    def __init__(self, response: GnnAnalysisResponse) -> None:
        self._response = response
        self.requests: list[GnnAnalysisRequest] = []

    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse:
        self.requests.append(request)
        return self._response

    def list_clusters(self, request: object) -> object:
        raise NotImplementedError


def test_gnn_graph_embedding_provider_maps_node_embeddings() -> None:
    gnn = _RecordingGnnService(
        GnnAnalysisResponse(
            request_id="gnn-1",
            knowledge_base_id="kb-1",
            node_count=2,
            edge_count=1,
            node_embeddings={
                "entity-1": [0.1, 0.2, 0.3],
                "entity-2": [0.4, 0.5, 0.6],
                "entity-3": [0.7, 0.8, 0.9],
            },
        )
    )
    provider = GnnGraphEmbeddingProvider(gnn)

    batch = provider.get_node_embeddings(
        knowledge_base_id="kb-1",
        content_ids=["entity-2", "entity-1"],
        dimensions=3,
    )

    assert gnn.requests[0].embedding_dimension == 3
    assert batch.model_name == "gnn-spectral"
    assert batch.provider == "analytics.gnn"
    assert list(batch.vectors) == ["entity-2", "entity-1"]
    assert batch.vectors["entity-1"] == [0.1, 0.2, 0.3]


def test_gnn_graph_embedding_provider_omits_unrequested_ids() -> None:
    gnn = _RecordingGnnService(
        GnnAnalysisResponse(
            request_id="gnn-1",
            knowledge_base_id="kb-1",
            node_count=2,
            edge_count=1,
            node_embeddings={
                "entity-1": [0.1, 0.2],
                "other": [0.9, 0.9],
            },
        )
    )
    provider = GnnGraphEmbeddingProvider(gnn)

    batch = provider.get_node_embeddings(
        knowledge_base_id="kb-1",
        content_ids=["entity-1", "missing"],
        dimensions=2,
    )

    assert batch.vectors == {"entity-1": [0.1, 0.2]}
