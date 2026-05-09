"""OpenAI embeddings adapter with conservative batching and retry handling."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
import importlib
import math
import os
import time
from typing import Protocol, SupportsFloat, cast, runtime_checkable

from config.schema import EmbeddingsConfig
from embeddings.exceptions import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)
from embeddings.models import (
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
)

__all__ = ["OpenAIEmbedder"]

_PROVIDER_NAME = "openai"
_MAX_INPUT_TOKENS = 8191
_CHARS_PER_TOKEN_ESTIMATE = 4
_MAX_RETRY_ATTEMPTS = 3


@runtime_checkable
class SupportsToList(Protocol):
    """Represent vector containers that can be materialized as Python lists."""

    def tolist(self) -> object: ...


class OpenAIEmbeddingsEndpointProtocol(Protocol):
    """Structural boundary for the OpenAI embeddings endpoint."""

    def create(self, *, input: Sequence[str], model: str) -> object: ...


class OpenAIClientProtocol(Protocol):
    """Structural boundary for the OpenAI client used by this adapter."""

    embeddings: OpenAIEmbeddingsEndpointProtocol


class OpenAIEmbedder:
    """Generate embeddings with the OpenAI embeddings API."""

    def __init__(
        self,
        config: EmbeddingsConfig,
        *,
        client: OpenAIClientProtocol | None = None,
        client_factory: Callable[[str], OpenAIClientProtocol] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        self._batch_size = max(config.batch_size, 1)
        self._dimensions = config.dimensions
        self._model_name = config.model
        self._sleep = sleep

        api_key_env_var = _validate_api_key_env_var(config.api_key_env_var)
        api_key = _read_api_key(
            api_key_env_var,
            environment=os.environ if environment is None else environment,
        )
        self._client = (
            client
            if client is not None
            else (client_factory or _create_openai_client)(api_key)
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Embed request items while respecting batch-size and token budgets."""

        vectors: dict[str, list[float]] = {}

        for batch in _iter_batches(
            request.items,
            batch_size=self._batch_size,
            token_limit=_MAX_INPUT_TOKENS,
        ):
            batch_vectors = self._embed_batch(batch)
            for item in batch:
                vectors[item.id] = batch_vectors[item.id]

        return EmbeddingResult(
            request_id=request.request_id,
            vectors=vectors,
            metadata=EmbeddingMetadata(
                model_name=self._model_name,
                dimensions=self._dimensions,
                provider=_PROVIDER_NAME,
            ),
        )

    def _embed_batch(self, items: Sequence[EmbeddingItem]) -> dict[str, list[float]]:
        """Send one provider batch and parse the resulting vectors."""

        texts = [item.content for item in items]
        response = self._create_embeddings_with_retry(texts)
        return _parse_embedding_response(
            response,
            items,
            expected_dimensions=self._dimensions,
        )

    def _create_embeddings_with_retry(self, texts: Sequence[str]) -> object:
        """Call the provider with exponential backoff for rate-limit failures."""

        attempt = 1
        while True:
            try:
                return self._client.embeddings.create(
                    input=texts,
                    model=self._model_name,
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise EmbeddingProviderError(
                        "OpenAI embeddings request failed."
                    ) from exc

                if attempt >= _MAX_RETRY_ATTEMPTS:
                    raise EmbeddingProviderError(
                        "OpenAI embeddings request exceeded the maximum "
                        "number of rate-limit retry attempts."
                    ) from exc

                self._sleep(float(2 ** (attempt - 1)))
                attempt += 1


def _validate_api_key_env_var(api_key_env_var: str | None) -> str:
    """Validate that the config identifies a usable API key environment variable."""

    if api_key_env_var is None or api_key_env_var.strip() == "":
        raise EmbeddingConfigurationError(
            "EmbeddingsConfig.api_key_env_var must be configured for the "
            "OpenAI embeddings adapter."
        )
    return api_key_env_var


def _read_api_key(api_key_env_var: str, *, environment: Mapping[str, str]) -> str:
    """Read and validate the configured API key from the environment."""

    api_key = environment.get(api_key_env_var)
    if api_key is None or api_key.strip() == "":
        raise EmbeddingConfigurationError(
            "OpenAI embeddings API key is missing. Set the environment "
            f"variable '{api_key_env_var}'."
        )
    return api_key


def _create_openai_client(api_key: str) -> OpenAIClientProtocol:
    """Create the OpenAI client only when the adapter is constructed."""

    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "The optional openai dependency is not installed. Install "
            "chili-backend[openai]."
        ) from exc

    constructor_object = getattr(openai_module, "OpenAI", None)
    if constructor_object is None or not callable(constructor_object):
        raise ImportError(
            "openai is installed, but OpenAI could not be imported."
        )

    constructor = cast(Callable[..., OpenAIClientProtocol], constructor_object)
    return constructor(api_key=api_key)


def _iter_batches(
    items: Sequence[EmbeddingItem],
    *,
    batch_size: int,
    token_limit: int,
) -> Iterator[list[EmbeddingItem]]:
    """Yield stable batches constrained by item count and estimated token use."""

    current_batch: list[EmbeddingItem] = []
    current_token_estimate = 0
    effective_batch_size = max(batch_size, 1)

    for item in items:
        estimated_tokens = _estimate_tokens(item.content)

        if estimated_tokens > token_limit:
            raise EmbeddingProviderError(
                "OpenAI embeddings input exceeds the per-request token limit "
                f"for item '{item.id}'. Estimated {estimated_tokens} tokens, "
                f"limit is {token_limit}."
            )

        would_exceed_batch_size = len(current_batch) >= effective_batch_size
        would_exceed_token_limit = (
            current_token_estimate + estimated_tokens > token_limit
        )
        if current_batch and (
            would_exceed_batch_size or would_exceed_token_limit
        ):
            yield current_batch
            current_batch = []
            current_token_estimate = 0

        current_batch.append(item)
        current_token_estimate += estimated_tokens

    if current_batch:
        yield current_batch


def _estimate_tokens(content: str) -> int:
    """Estimate token usage conservatively without a tokenizer dependency."""

    return max(1, math.ceil(len(content) / _CHARS_PER_TOKEN_ESTIMATE))


def _parse_embedding_response(
    response: object,
    items: Sequence[EmbeddingItem],
    *,
    expected_dimensions: int,
) -> dict[str, list[float]]:
    """Map an OpenAI embeddings response back to item IDs in stable order."""

    data_object = getattr(response, "data", None)
    if not isinstance(data_object, Sequence) or isinstance(
        data_object, str | bytes
    ):
        raise EmbeddingProviderError(
            "OpenAI embeddings response did not include a usable data "
            "sequence."
        )

    records = list(cast(Sequence[object], data_object))
    if len(records) != len(items):
        raise EmbeddingProviderError(
            "OpenAI returned a different number of vectors than requested. "
            f"Expected {len(items)}, received {len(records)}."
        )

    vectors_by_index: dict[int, list[float]] = {}
    for fallback_index, record in enumerate(records):
        item_index = _coerce_record_index(
            getattr(record, "index", fallback_index),
            upper_bound=len(items),
        )
        if item_index in vectors_by_index:
            raise EmbeddingProviderError(
                "OpenAI embeddings response contained duplicate indexes."
            )

        item = items[item_index]
        vector = _coerce_vector(getattr(record, "embedding", None), item_id=item.id)
        if len(vector) != expected_dimensions:
            raise EmbeddingProviderError(
                "OpenAI returned an unexpected vector dimension for item "
                f"'{item.id}'. Expected {expected_dimensions}, received "
                f"{len(vector)}."
            )
        vectors_by_index[item_index] = vector

    return {items[index].id: vectors_by_index[index] for index in range(len(items))}


def _coerce_record_index(index_value: object, *, upper_bound: int) -> int:
    """Validate provider record indexes before mapping them to request items."""

    if not isinstance(index_value, int):
        raise EmbeddingProviderError(
            "OpenAI embeddings response contained a non-integer index."
        )
    if index_value < 0 or index_value >= upper_bound:
        raise EmbeddingProviderError(
            "OpenAI embeddings response contained an out-of-range index."
        )
    return index_value


def _coerce_vector(raw_vector: object, *, item_id: str) -> list[float]:
    """Convert provider vectors into plain Python float lists."""

    materialized: object
    if isinstance(raw_vector, SupportsToList):
        materialized = raw_vector.tolist()
    else:
        materialized = raw_vector

    if not isinstance(materialized, Sequence) or isinstance(
        materialized, str | bytes
    ):
        raise EmbeddingProviderError(
            "OpenAI returned a non-sequence vector for item "
            f"'{item_id}'."
        )

    vector: list[float] = []
    for value in cast(Sequence[object], materialized):
        try:
            vector.append(_coerce_float(value))
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "OpenAI returned a vector containing a non-numeric value for "
                f"item '{item_id}'."
            ) from exc
    return vector


def _coerce_float(value: object) -> float:
    """Convert numeric provider scalar values into floats."""

    if isinstance(value, (float, int)):
        return float(value)
    if hasattr(value, "__float__"):
        return float(cast(SupportsFloat, value))
    raise TypeError("Embedding value is not numeric.")


def _is_rate_limit_error(error: Exception) -> bool:
    """Detect provider rate-limit errors without importing SDK-specific types."""

    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if response_status == 429:
        return True

    return "ratelimit" in type(error).__name__.lower()