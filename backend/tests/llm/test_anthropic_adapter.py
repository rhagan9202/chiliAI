"""Tests for the Anthropic LLM adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest

from config.schema import LlmConfig
from llm.adapters.anthropic_adapter import (
    AnthropicClientProtocol,
    AnthropicLlmClient,
)
from llm.exceptions import LlmConfigurationError, LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole


@dataclass(frozen=True)
class MessageCall:
    """Record the payload sent to the fake Anthropic messages endpoint."""

    model: str
    messages: list[dict[str, str]]
    temperature: float
    max_tokens: int
    system: str | None


@dataclass(frozen=True)
class FakeContentBlock:
    """Represent one content block in a fake Anthropic response."""

    text: str | None = None


@dataclass(frozen=True)
class FakeUsage:
    """Represent optional Anthropic token usage metadata."""

    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class FakeMessageResponse:
    """Represent the fake API response surface used by the adapter."""

    content: list[FakeContentBlock]
    usage: FakeUsage | None = None


class FakeRateLimitError(Exception):
    """Fake provider error that mimics Anthropic rate-limit failures."""

    def __init__(self) -> None:
        super().__init__("rate limited")
        self.status_code = 429


class FakeResponseRateLimitError(Exception):
    """Fake provider error that exposes a 429 via response.status_code."""

    def __init__(self) -> None:
        super().__init__("rate limited")
        self.response = type("Response", (), {"status_code": 429})()


class FakeMessagesRateLimitError(Exception):
    """Fake provider error whose class name implies a rate limit."""


class FakeMessagesEndpoint:
    """Fake messages endpoint with queued responses or exceptions."""

    def __init__(self, *, outcomes: list[object] | None = None) -> None:
        self._outcomes = list(outcomes or [])
        self.calls: list[MessageCall] = []

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        system: str | None = None,
    ) -> object:
        self.calls.append(
            MessageCall(
                model=model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                system=system,
            )
        )

        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return FakeMessageResponse(content=[FakeContentBlock(text="Default reply")])


class FakeAnthropicClient:
    """Fake Anthropic client exposing only the messages endpoint used here."""

    def __init__(self, endpoint: FakeMessagesEndpoint) -> None:
        self.messages = endpoint

    def __bool__(self) -> bool:
        """Ensure adapter client injection does not depend on truthiness."""

        return False


def test_anthropic_llm_client_reads_api_key_from_configured_env_var() -> None:
    captured_api_keys: list[str] = []

    def build_client(api_key: str) -> AnthropicClientProtocol:
        captured_api_keys.append(api_key)
        return cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(FakeMessagesEndpoint()),
        )

    AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client_factory=build_client,
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    assert captured_api_keys == ["test-api-key"]


@pytest.mark.parametrize("env_var_name", [None, "", "   "])
def test_anthropic_llm_client_requires_api_key_env_var_configuration(
    env_var_name: str | None,
) -> None:
    with pytest.raises(LlmConfigurationError, match="api_key_env_var"):
        AnthropicLlmClient(
            LlmConfig(
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                api_key_env_var=env_var_name,
            ),
            client=cast(
                AnthropicClientProtocol,
                FakeAnthropicClient(FakeMessagesEndpoint()),
            ),
            environment={"ANTHROPIC_API_KEY": "unused"},
        )


@pytest.mark.parametrize("environment", [{}, {"ANTHROPIC_API_KEY": "   "}])
def test_anthropic_llm_client_requires_environment_value(
    environment: dict[str, str],
) -> None:
    with pytest.raises(LlmConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicLlmClient(
            LlmConfig(
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                api_key_env_var="ANTHROPIC_API_KEY",
            ),
            client=cast(
                AnthropicClientProtocol,
                FakeAnthropicClient(FakeMessagesEndpoint()),
            ),
            environment=environment,
        )


def test_anthropic_llm_client_constructs_requests_and_maps_usage() -> None:
    messages_endpoint = FakeMessagesEndpoint(
        outcomes=[
            FakeMessageResponse(
                content=[
                    FakeContentBlock(text="Summarized "),
                    FakeContentBlock(text="findings"),
                ],
                usage=FakeUsage(input_tokens=21, output_tokens=11),
            )
        ]
    )
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    result = client.generate(
        GenerationRequest(
            request_id="request-1",
            messages=[
                ChatMessage(role=MessageRole.SYSTEM, content="Be concise."),
                ChatMessage(role=MessageRole.USER, content="Summarize findings"),
                ChatMessage(role=MessageRole.SYSTEM, content="Use bullets if useful."),
                ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content="Previous assistant context.",
                ),
            ],
            model_name="ignored-by-adapter",
            temperature=0.35,
            max_tokens=128,
        )
    )

    assert messages_endpoint.calls == [
        MessageCall(
            model="claude-sonnet-4-20250514",
            messages=[
                {"role": "user", "content": "Summarize findings"},
                {
                    "role": "assistant",
                    "content": "Previous assistant context.",
                },
            ],
            temperature=0.35,
            max_tokens=128,
            system="Be concise.\n\nUse bullets if useful.",
        )
    ]
    assert result.request_id == "request-1"
    assert result.completion == "Summarized findings"
    assert result.metadata.provider == "anthropic"
    assert result.metadata.model_name == "claude-sonnet-4-20250514"
    assert result.metadata.temperature == 0.35
    assert result.metadata.max_tokens == 128
    assert result.metadata.prompt_tokens == 21
    assert result.metadata.completion_tokens == 11


def test_anthropic_llm_client_leaves_usage_fields_empty_when_missing() -> None:
    messages_endpoint = FakeMessagesEndpoint(
        outcomes=[
            FakeMessageResponse(content=[FakeContentBlock(text="No usage block")])
        ]
    )
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    result = client.generate(
        GenerationRequest(
            request_id="request-2",
            messages=[ChatMessage(role=MessageRole.USER, content="Hello there")],
            model_name="ignored",
        )
    )

    assert result.metadata.prompt_tokens is None
    assert result.metadata.completion_tokens is None


def test_anthropic_llm_client_rejects_invalid_usage_metadata() -> None:
    messages_endpoint = FakeMessagesEndpoint(
        outcomes=[
            FakeMessageResponse(
                content=[FakeContentBlock(text="Bad usage")],
                usage=FakeUsage(input_tokens=-1),
            )
        ]
    )
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="input_tokens"):
        client.generate(
            GenerationRequest(
                request_id="request-3",
                messages=[ChatMessage(role=MessageRole.USER, content="Hello there")],
                model_name="ignored",
            )
        )


def test_anthropic_llm_client_rejects_responses_without_usable_text() -> None:
    messages_endpoint = FakeMessagesEndpoint(
        outcomes=[
            FakeMessageResponse(
                content=[FakeContentBlock(text=None), FakeContentBlock(text="   ")]
            )
        ]
    )
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="usable text content"):
        client.generate(
            GenerationRequest(
                request_id="request-4",
                messages=[ChatMessage(role=MessageRole.USER, content="Hello there")],
                model_name="ignored",
            )
        )


def test_anthropic_llm_client_rejects_requests_with_only_system_messages() -> None:
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(FakeMessagesEndpoint()),
        ),
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="at least one non-system"):
        client.generate(
            GenerationRequest(
                request_id="request-5",
                messages=[
                    ChatMessage(role=MessageRole.SYSTEM, content="System only")
                ],
                model_name="ignored",
            )
        )


@pytest.mark.parametrize(
    "error_factory",
    [
        FakeRateLimitError,
        FakeResponseRateLimitError,
        lambda: FakeMessagesRateLimitError("slow down"),
    ],
)
def test_anthropic_llm_client_retries_rate_limit_errors_with_backoff(
    error_factory: Callable[[], Exception],
) -> None:
    messages_endpoint = FakeMessagesEndpoint(
        outcomes=[
            error_factory(),
            error_factory(),
            FakeMessageResponse(content=[FakeContentBlock(text="Recovered")]),
        ]
    )
    sleep_calls: list[float] = []
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        sleep=sleep_calls.append,
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    result = client.generate(
        GenerationRequest(
            request_id="request-6",
            messages=[ChatMessage(role=MessageRole.USER, content="Retry please")],
            model_name="ignored",
        )
    )

    assert sleep_calls == [1.0, 2.0]
    assert len(messages_endpoint.calls) == 3
    assert result.completion == "Recovered"


def test_anthropic_llm_client_stops_after_max_rate_limit_attempts() -> None:
    messages_endpoint = FakeMessagesEndpoint(
        outcomes=[FakeRateLimitError(), FakeRateLimitError(), FakeRateLimitError()]
    )
    sleep_calls: list[float] = []
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        sleep=sleep_calls.append,
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="maximum number of rate-limit"):
        client.generate(
            GenerationRequest(
                request_id="request-7",
                messages=[ChatMessage(role=MessageRole.USER, content="Retry please")],
                model_name="ignored",
            )
        )

    assert sleep_calls == [1.0, 2.0]
    assert len(messages_endpoint.calls) == 3


def test_anthropic_llm_client_does_not_retry_non_rate_limit_errors() -> None:
    messages_endpoint = FakeMessagesEndpoint(outcomes=[RuntimeError("boom")])
    sleep_calls: list[float] = []
    client = AnthropicLlmClient(
        LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        client=cast(
            AnthropicClientProtocol,
            FakeAnthropicClient(messages_endpoint),
        ),
        sleep=sleep_calls.append,
        environment={"ANTHROPIC_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="request failed"):
        client.generate(
            GenerationRequest(
                request_id="request-8",
                messages=[ChatMessage(role=MessageRole.USER, content="Fail fast")],
                model_name="ignored",
            )
        )

    assert sleep_calls == []
    assert len(messages_endpoint.calls) == 1