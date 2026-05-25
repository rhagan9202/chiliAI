"""Composition adapter from GNN analysis to embeddings graph provider."""

from __future__ import annotations

from collections.abc import Sequence

from analytics.gnn.protocols import GnnServiceProtocol
from analytics.gnn.service_models import GnnAnalysisRequest
from embeddings.adapters.protocols import GraphEmbeddingProviderProtocol
from embeddings.models import GraphEmbeddingBatch

__all__ = ["GnnGraphEmbeddingProvider"]


class GnnGraphEmbeddingProvider(GraphEmbeddingProviderProtocol):
    """Expose GNN node embeddings through the embeddings-local protocol."""

    def __init__(
        self,
        gnn_service: GnnServiceProtocol,
        *,
        model_name: str = "gnn-spectral",
        provider: str = "analytics.gnn",
    ) -> None:
        self._gnn_service = gnn_service
        self._model_name = model_name
        self._provider = provider

    def get_node_embeddings(
        self,
        *,
        knowledge_base_id: str,
        content_ids: Sequence[str],
        dimensions: int,
    ) -> GraphEmbeddingBatch:
        response = self._gnn_service.analyze(
            GnnAnalysisRequest(
                knowledge_base_id=knowledge_base_id,
                embedding_dimension=dimensions,
            )
        )
        vectors = {
            content_id: list(response.node_embeddings[content_id])
            for content_id in content_ids
            if content_id in response.node_embeddings
        }
        return GraphEmbeddingBatch(
            vectors=vectors,
            model_name=self._model_name,
            provider=self._provider,
            dimensions=dimensions,
        )
