"""In-memory embedder for tests and local development."""

from __future__ import annotations

from embeddings.models import EmbeddingMetadata, EmbeddingRequest, EmbeddingResult


class InMemoryEmbedder:
    """A deterministic embedder that converts text statistics into fixed-size vectors."""

    def __init__(self, *, provider: str = "in-memory") -> None:
        self._provider = provider

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        vectors = {
            item.id: _embed_text(item.content)
            for item in request.items
        }
        dimensions = len(next(iter(vectors.values())))
        return EmbeddingResult(
            request_id=request.request_id,
            vectors=vectors,
            metadata=EmbeddingMetadata(
                model_name=request.model_name,
                dimensions=dimensions,
                provider=self._provider,
            ),
        )


def _embed_text(content: str) -> list[float]:
    text = content.strip()
    return [
        float(len(text)),
        float(sum(1 for char in text if char.isalpha())),
        float(sum(1 for char in text if char.isdigit())),
        float(len(text.split())),
    ]