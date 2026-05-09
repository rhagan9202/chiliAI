"""Sentence-transformers adapter for local embedding generation."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
import importlib
import math
from typing import Protocol, SupportsFloat, cast, runtime_checkable

from config.schema import EmbeddingsConfig
from embeddings.exceptions import EmbeddingProviderError
from embeddings.models import (
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
)

__all__ = ["SentenceTransformersEmbedder"]

_PROVIDER_NAME = "sentence-transformers"


@runtime_checkable
class SupportsToList(Protocol):
    """Represent a vector container that can materialize to Python lists."""

    def tolist(self) -> object: ...


EncodedBatch = Sequence[object] | SupportsToList


class SentenceTransformerModelProtocol(Protocol):
    """Structural contract for the sentence-transformers model boundary."""

    def encode(
        self,
        sentences: Sequence[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        normalize_embeddings: bool,
    ) -> EncodedBatch: ...


class SentenceTransformersEmbedder:
    """Generate embeddings locally with a reusable sentence-transformers model."""

    def __init__(
        self,
        config: EmbeddingsConfig,
        *,
        model: SentenceTransformerModelProtocol | None = None,
        model_loader: Callable[[str], SentenceTransformerModelProtocol] | None = None,
    ) -> None:
        self._config = config
        self._batch_size = max(config.batch_size, 1)
        self._dimensions = config.dimensions
        self._model_name = config.model
        self._model = model or (model_loader or _load_sentence_transformer_model)(
            self._model_name
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Embed request items in batches and return normalized vectors."""

        vectors: dict[str, list[float]] = {}

        for batch in _iter_batches(request.items, self._batch_size):
            encoded_vectors = self._encode_batch(batch)
            for item, vector in zip(batch, encoded_vectors, strict=True):
                vectors[item.id] = vector

        return EmbeddingResult(
            request_id=request.request_id,
            vectors=vectors,
            metadata=EmbeddingMetadata(
                model_name=self._model_name,
                dimensions=self._dimensions,
                provider=_PROVIDER_NAME,
            ),
        )

    def _encode_batch(self, items: Sequence[EmbeddingItem]) -> list[list[float]]:
        """Encode a single batch and validate the returned vector shape."""

        texts = [item.content for item in items]
        raw_batch = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=False,
        )
        materialized_batch = _materialize_batch(raw_batch)

        if len(materialized_batch) != len(items):
            raise EmbeddingProviderError(
                "Sentence-transformers returned a different number of vectors "
                f"than requested. Expected {len(items)}, received "
                f"{len(materialized_batch)}."
            )

        normalized_vectors: list[list[float]] = []
        for item, raw_vector in zip(items, materialized_batch, strict=True):
            item_id = item.id
            vector = _coerce_vector(raw_vector, item_id=item_id)
            if len(vector) != self._dimensions:
                raise EmbeddingProviderError(
                    "Sentence-transformers returned an unexpected vector "
                    f"dimension for item '{item_id}'. Expected "
                    f"{self._dimensions}, received {len(vector)}."
                )
            normalized_vectors.append(_normalize_vector(vector, item_id=item_id))

        return normalized_vectors


def _load_sentence_transformer_model(
    model_name: str,
) -> SentenceTransformerModelProtocol:
    """Load the sentence-transformers model only when the adapter is used."""

    try:
        sentence_transformers_module = importlib.import_module(
            "sentence_transformers"
        )
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "The optional sentence-transformers dependency is not installed. "
            "Install chili-backend[sentence-transformers]."
        ) from exc

    constructor_object = getattr(
        sentence_transformers_module,
        "SentenceTransformer",
        None,
    )
    if constructor_object is None or not callable(constructor_object):
        raise ImportError(
            "sentence-transformers is installed, but SentenceTransformer "
            "could not be imported."
        )

    constructor = cast(
        Callable[[str], SentenceTransformerModelProtocol],
        constructor_object,
    )
    return constructor(model_name)


def _iter_batches(
    items: Sequence[EmbeddingItem],
    batch_size: int,
) -> Iterator[Sequence[EmbeddingItem]]:
    """Yield stable slices of items sized for provider batch limits."""

    for start_index in range(0, len(items), max(batch_size, 1)):
        yield items[start_index : start_index + max(batch_size, 1)]


def _materialize_batch(raw_batch: EncodedBatch) -> list[object]:
    """Convert provider output into a concrete list of raw vector objects."""

    materialized: object
    if isinstance(raw_batch, SupportsToList):
        materialized = raw_batch.tolist()
    else:
        materialized = raw_batch

    if not isinstance(materialized, Sequence) or isinstance(materialized, str | bytes):
        raise EmbeddingProviderError(
            "Sentence-transformers returned embeddings in an unsupported format."
        )

    return list(cast(Sequence[object], materialized))


def _coerce_vector(raw_vector: object, *, item_id: str) -> list[float]:
    """Convert a raw provider vector into Python floats."""

    materialized: object
    if isinstance(raw_vector, SupportsToList):
        materialized = raw_vector.tolist()
    else:
        materialized = raw_vector

    if not isinstance(materialized, Sequence) or isinstance(materialized, str | bytes):
        raise EmbeddingProviderError(
            "Sentence-transformers returned a non-sequence vector for item "
            f"'{item_id}'."
        )

    sequence = cast(Sequence[object], materialized)
    vector: list[float] = []
    for value in sequence:
        try:
            vector.append(_coerce_float(value))
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "Sentence-transformers returned a vector containing a "
                f"non-numeric value for item '{item_id}'."
            ) from exc
    return vector


def _normalize_vector(vector: Sequence[float], *, item_id: str) -> list[float]:
    """Normalize vectors to unit length for cosine-similarity semantics."""

    norm = math.sqrt(sum(component * component for component in vector))
    if norm <= 0.0:
        raise EmbeddingProviderError(
            "Sentence-transformers returned a zero vector for item "
            f"'{item_id}'."
        )

    return [component / norm for component in vector]


def _coerce_float(value: object) -> float:
    """Convert provider scalar values into floats with strict typing."""

    if isinstance(value, (float, int, str)):
        return float(value)
    if hasattr(value, "__float__"):
        return float(cast(SupportsFloat, value))
    raise TypeError("Embedding value is not numeric.")