"""In-memory embedder for tests and local development."""

from __future__ import annotations

import hashlib
import math
import re

from embeddings.models import EmbeddingMetadata, EmbeddingRequest, EmbeddingResult

__all__ = ["InMemoryEmbedder"]


class InMemoryEmbedder:
    """A deterministic embedder that converts text statistics into fixed-size vectors."""

    def __init__(self, *, provider: str = "in-memory", dimensions: int = 384) -> None:
        if dimensions <= 0:
            raise ValueError("InMemoryEmbedder dimensions must be positive.")
        self._provider = provider
        self._dimensions = dimensions

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        vectors = {
            item.id: _embed_text(item.content, self._dimensions)
            for item in request.items
        }
        return EmbeddingResult(
            request_id=request.request_id,
            vectors=vectors,
            metadata=EmbeddingMetadata(
                model_name=request.model_name,
                dimensions=self._dimensions,
                provider=self._provider,
            ),
        )


def _embed_text(content: str, dimensions: int) -> list[float]:
    text = content.strip()
    tokens = re.findall(r"\w+|[^\w\s]", text.lower()) or ["<empty>"]
    vector = [0.0] * dimensions

    for position, token in enumerate(tokens):
        features = (
            token,
            f"{position}:{token}",
            f"len:{len(token)}",
        )
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            weight = 1.0 + min(len(token), 32) / 32.0
            vector[bucket] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]
