"""Production query embedder adapter that delegates to the embeddings service."""

from __future__ import annotations

from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service_models import EmbeddedItem, EmbedRequest, EmbedSubmission
from rag.exceptions import RagConfigurationError


class ServiceQueryEmbedder:
    """Adapter that satisfies `QueryEmbedderProtocol` via `EmbeddingsServiceProtocol`."""

    def __init__(
        self,
        service: EmbeddingsServiceProtocol,
        *,
        model_name: str | None = None,
        content_id: str = "rag-query",
    ) -> None:
        self._service = service
        self._model_name = model_name
        self._content_id = content_id

    def embed_query(self, *, knowledge_base_id: str, question: str) -> list[float]:
        if question.strip() == "":
            raise RagConfigurationError("Query embedding requires a non-empty question.")

        submission = EmbedSubmission(content_id=self._content_id, content=question)
        request_kwargs: dict[str, object] = {
            "knowledge_base_id": knowledge_base_id,
            "submissions": [submission],
        }
        if self._model_name is not None:
            request_kwargs["model_name"] = self._model_name

        request = EmbedRequest.model_validate(request_kwargs)
        response = self._service.embed(request)

        items: list[EmbeddedItem] = list(response.items)
        if not items:
            raise RagConfigurationError(
                "Embeddings service returned no items for the query embedding request."
            )

        vector = list(items[0].vector)
        if not vector:
            raise RagConfigurationError(
                "Embeddings service returned an empty vector for the query embedding request."
            )
        return vector


__all__ = ["ServiceQueryEmbedder"]
