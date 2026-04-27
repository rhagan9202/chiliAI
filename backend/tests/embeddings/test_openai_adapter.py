"""Tests for the OpenAI embeddings adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from config.schema import EmbeddingsConfig
from embeddings.adapters.openai_adapter import (
    OpenAIClientProtocol,
    OpenAIEmbedder,
)
from embeddings.exceptions import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)
from embeddings.models import EmbeddingItem, EmbeddingRequest


@dataclass(frozen=True)
class EmbeddingCall:
    """Record the payload sent to the fake OpenAI endpoint."""

    model: str
    inputs: list[str]


@dataclass(frozen=True)
class FakeEmbeddingRecord:
    """Represent one embedding row in a fake API response."""

    index: int
    embedding: list[float]


@dataclass(frozen=True)
class FakeEmbeddingResponse:
    """Represent the fake API response surface used by the adapter."""

    data: list[FakeEmbeddingRecord]


class FakeRateLimitError(Exception):
    """Fake provider error that mimics OpenAI rate-limit failures."""

    def __init__(self) -> None:
        super().__init__("rate limited")
        self.status_code = 429


class FakeEmbeddingsEndpoint:
    """Fake embeddings endpoint with queued responses or exceptions."""

    def __init__(
        self,
        *,
        vector_size: int = 3,
        outcomes: list[object] | None = None,
        reverse_response_order: bool = False,
    ) -> None:
        self._vector_size = vector_size
        self._outcomes = list(outcomes or [])
        self._reverse_response_order = reverse_response_order
        self.calls: list[EmbeddingCall] = []

    def create(self, *, input: list[str] | tuple[str, ...], model: str) -> object:
        inputs = list(input)
        self.calls.append(EmbeddingCall(model=model, inputs=inputs))

        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        records = [
            FakeEmbeddingRecord(index=index, embedding=_vector_for_text(text))
            for index, text in enumerate(inputs)
        ]
        if self._reverse_response_order:
            records.reverse()
        return FakeEmbeddingResponse(data=records)


class FakeOpenAIClient:
    """Fake OpenAI client exposing only the embeddings endpoint used here."""

    def __init__(self, endpoint: FakeEmbeddingsEndpoint) -> None:
        self.embeddings = endpoint

    def __bool__(self) -> bool:
        """Ensure adapter client injection does not depend on truthiness."""

        return False


def test_openai_embedder_reads_api_key_from_configured_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    captured_api_keys: list[str] = []

    def build_client(api_key: str) -> OpenAIClientProtocol:
        captured_api_keys.append(api_key)
        return cast(OpenAIClientProtocol, FakeOpenAIClient(FakeEmbeddingsEndpoint()))

    OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=4,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client_factory=build_client,
    )

    assert captured_api_keys == ["test-api-key"]


@pytest.mark.parametrize("env_var_name", [None, "", "   "])
def test_openai_embedder_requires_api_key_env_var_configuration(
    env_var_name: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "unused")

    with pytest.raises(EmbeddingConfigurationError, match="api_key_env_var"):
        OpenAIEmbedder(
            EmbeddingsConfig(
                provider="openai",
                model="text-embedding-3-small",
                dimensions=3,
                batch_size=4,
                api_key_env_var=env_var_name,
            ),
            client=cast(OpenAIClientProtocol, FakeOpenAIClient(FakeEmbeddingsEndpoint())),
        )


def test_openai_embedder_requires_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(EmbeddingConfigurationError, match="OPENAI_API_KEY"):
        OpenAIEmbedder(
            EmbeddingsConfig(
                provider="openai",
                model="text-embedding-3-small",
                dimensions=3,
                batch_size=4,
                api_key_env_var="OPENAI_API_KEY",
            ),
            client=cast(OpenAIClientProtocol, FakeOpenAIClient(FakeEmbeddingsEndpoint())),
        )


def test_openai_embedder_constructs_requests_and_preserves_item_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(reverse_response_order=True)
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=8,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-1",
            model_name="ignored-at-runtime",
            items=[
                EmbeddingItem(id="item-1", content="Alpha"),
                EmbeddingItem(id="item-2", content="Beta 123"),
            ],
        )
    )

    assert endpoint.calls == [
        EmbeddingCall(
            model="text-embedding-3-small",
            inputs=["Alpha", "Beta 123"],
        )
    ]
    assert list(result.vectors) == ["item-1", "item-2"]
    assert result.vectors["item-1"] == _vector_for_text("Alpha")
    assert result.vectors["item-2"] == _vector_for_text("Beta 123")
    assert result.metadata.provider == "openai"
    assert result.metadata.model_name == "text-embedding-3-small"
    assert result.metadata.dimensions == 3


def test_openai_embedder_batches_by_batch_size_and_token_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint()
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=3,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    medium_a = "a" * 12000
    medium_b = "b" * 16000
    medium_c = "c" * 8000

    embedder.embed(
        EmbeddingRequest(
            request_id="request-2",
            model_name="ignored-at-runtime",
            items=[
                EmbeddingItem(id="item-1", content=medium_a),
                EmbeddingItem(id="item-2", content=medium_b),
                EmbeddingItem(id="item-3", content=medium_c),
            ],
        )
    )

    assert [call.inputs for call in endpoint.calls] == [
        [medium_a, medium_b],
        [medium_c],
    ]


def test_openai_embedder_rejects_single_input_over_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint()
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=3,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    with pytest.raises(EmbeddingProviderError, match="exceeds the per-request token limit"):
        embedder.embed(
            EmbeddingRequest(
                request_id="request-too-large",
                model_name="ignored-at-runtime",
                items=[EmbeddingItem(id="item-1", content="d" * 40000)],
            )
        )

    assert endpoint.calls == []


def test_openai_embedder_retries_rate_limit_errors_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(
        outcomes=[FakeRateLimitError(), FakeRateLimitError()],
    )
    sleep_calls: list[float] = []
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=8,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
        sleep=sleep_calls.append,
    )

    result = embedder.embed(
        EmbeddingRequest(
            request_id="request-3",
            model_name="ignored-at-runtime",
            items=[EmbeddingItem(id="item-1", content="retry me")],
        )
    )

    assert sleep_calls == [1.0, 2.0]
    assert len(endpoint.calls) == 3
    assert result.vectors["item-1"] == _vector_for_text("retry me")


def test_openai_embedder_does_not_retry_non_rate_limit_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(outcomes=[RuntimeError("boom")])
    sleep_calls: list[float] = []
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=8,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
        sleep=sleep_calls.append,
    )

    with pytest.raises(EmbeddingProviderError, match="request failed"):
        embedder.embed(
            EmbeddingRequest(
                request_id="request-4",
                model_name="ignored-at-runtime",
                items=[EmbeddingItem(id="item-1", content="fail fast")],
            )
        )

    assert sleep_calls == []
    assert len(endpoint.calls) == 1


def test_openai_embedder_rejects_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    endpoint = FakeEmbeddingsEndpoint(
        outcomes=[
            FakeEmbeddingResponse(
                data=[FakeEmbeddingRecord(index=0, embedding=[1.0, 2.0])]
            )
        ]
    )
    embedder = OpenAIEmbedder(
        EmbeddingsConfig(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            batch_size=8,
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(endpoint)),
    )

    with pytest.raises(EmbeddingProviderError, match="Expected 3, received 2"):
        embedder.embed(
            EmbeddingRequest(
                request_id="request-5",
                model_name="ignored-at-runtime",
                items=[EmbeddingItem(id="item-1", content="Alpha")],
            )
        )


def _vector_for_text(text: str) -> list[float]:
    """Build a deterministic fake vector from input text."""

    return [
        float(len(text)),
        float(sum(1 for char in text if char.isalpha())),
        float(sum(1 for char in text if char.isdigit()) + len(text.split())),
    ]