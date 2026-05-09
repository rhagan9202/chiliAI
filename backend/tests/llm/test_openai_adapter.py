"""Tests for the OpenAI LLM adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest

from config.schema import LlmConfig
from llm.adapters.openai_adapter import OpenAIClientProtocol, OpenAILlmClient
from llm.exceptions import LlmConfigurationError, LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole


@dataclass(frozen=True)
class CompletionCall:
    """Record the payload sent to the fake completions endpoint."""

    model: str
    messages: list[dict[str, str]]
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class FakeChatMessage:
    """Represent one message returned by the fake API response."""

    content: str | None


@dataclass(frozen=True)
class FakeChoice:
    """Represent one fake completion choice."""

    message: FakeChatMessage


@dataclass(frozen=True)
class FakeUsage:
    """Represent optional token usage metadata."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class FakeCompletionResponse:
    """Represent the fake API response surface used by the adapter."""

    choices: list[FakeChoice]
    usage: FakeUsage | None = None


class FakeRateLimitError(Exception):
    """Fake provider error that mimics OpenAI rate-limit failures."""

    def __init__(self) -> None:
        super().__init__("rate limited")
        self.status_code = 429


class FakeResponseRateLimitError(Exception):
    """Fake provider error that exposes a 429 via response.status_code."""

    def __init__(self) -> None:
        super().__init__("rate limited")
        self.response = type("Response", (), {"status_code": 429})()


class FakeChatRateLimitError(Exception):
    """Fake provider error whose class name implies a rate limit."""


class FakeChatCompletionsEndpoint:
    """Fake completions endpoint with queued responses or exceptions."""

    def __init__(self, *, outcomes: list[object] | None = None) -> None:
        self._outcomes = list(outcomes or [])
        self.calls: list[CompletionCall] = []

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> object:
        self.calls.append(
            CompletionCall(
                model=model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return FakeCompletionResponse(
            choices=[FakeChoice(message=FakeChatMessage(content="Default reply"))]
        )


class FakeChat:
    """Fake chat API exposing completions."""

    def __init__(self, completions: FakeChatCompletionsEndpoint) -> None:
        self.completions = completions


class FakeOpenAIClient:
    """Fake OpenAI client exposing only the chat endpoint used here."""

    def __init__(self, completions: FakeChatCompletionsEndpoint) -> None:
        self.chat = FakeChat(completions)

    def __bool__(self) -> bool:
        """Ensure adapter client injection does not depend on truthiness."""

        return False


def test_openai_llm_client_reads_api_key_from_configured_env_var() -> None:
    captured_api_keys: list[str] = []

    def build_client(api_key: str) -> OpenAIClientProtocol:
        captured_api_keys.append(api_key)
        return cast(
            OpenAIClientProtocol,
            FakeOpenAIClient(FakeChatCompletionsEndpoint()),
        )

    OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client_factory=build_client,
        environment={"OPENAI_API_KEY": "test-api-key"},
    )

    assert captured_api_keys == ["test-api-key"]


@pytest.mark.parametrize("env_var_name", [None, "", "   "])
def test_openai_llm_client_requires_api_key_env_var_configuration(
    env_var_name: str | None,
) -> None:
    with pytest.raises(LlmConfigurationError, match="api_key_env_var"):
        OpenAILlmClient(
            LlmConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key_env_var=env_var_name,
            ),
            client=cast(
                OpenAIClientProtocol,
                FakeOpenAIClient(FakeChatCompletionsEndpoint()),
            ),
            environment={"OPENAI_API_KEY": "unused"},
        )


@pytest.mark.parametrize("environment", [{}, {"OPENAI_API_KEY": "   "}])
def test_openai_llm_client_requires_environment_value(
    environment: dict[str, str],
) -> None:
    with pytest.raises(LlmConfigurationError, match="OPENAI_API_KEY"):
        OpenAILlmClient(
            LlmConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key_env_var="OPENAI_API_KEY",
            ),
            client=cast(
                OpenAIClientProtocol,
                FakeOpenAIClient(FakeChatCompletionsEndpoint()),
            ),
            environment=environment,
        )


def test_openai_llm_client_constructs_requests_and_maps_usage() -> None:
    completions = FakeChatCompletionsEndpoint(
        outcomes=[
            FakeCompletionResponse(
                choices=[
                    FakeChoice(
                        message=FakeChatMessage(content="Summarized findings")
                    )
                ],
                usage=FakeUsage(prompt_tokens=17, completion_tokens=9),
            )
        ]
    )
    client = OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(completions)),
        environment={"OPENAI_API_KEY": "test-api-key"},
    )

    result = client.generate(
        GenerationRequest(
            request_id="request-1",
            messages=[
                ChatMessage(role=MessageRole.SYSTEM, content="Be concise."),
                ChatMessage(role=MessageRole.USER, content="Summarize findings"),
            ],
            model_name="ignored-by-adapter",
            temperature=0.35,
            max_tokens=128,
        )
    )

    assert completions.calls == [
        CompletionCall(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Summarize findings"},
            ],
            temperature=0.35,
            max_tokens=128,
        )
    ]
    assert result.request_id == "request-1"
    assert result.completion == "Summarized findings"
    assert result.metadata.provider == "openai"
    assert result.metadata.model_name == "gpt-4o-mini"
    assert result.metadata.temperature == 0.35
    assert result.metadata.max_tokens == 128
    assert result.metadata.prompt_tokens == 17
    assert result.metadata.completion_tokens == 9


def test_openai_llm_client_leaves_usage_fields_empty_when_missing() -> None:
    completions = FakeChatCompletionsEndpoint(
        outcomes=[
            FakeCompletionResponse(
                choices=[FakeChoice(message=FakeChatMessage(content="No usage block"))]
            )
        ]
    )
    client = OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(completions)),
        environment={"OPENAI_API_KEY": "test-api-key"},
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


def test_openai_llm_client_rejects_blank_completion_content() -> None:
    completions = FakeChatCompletionsEndpoint(
        outcomes=[
            FakeCompletionResponse(
                choices=[FakeChoice(message=FakeChatMessage(content="   "))]
            )
        ]
    )
    client = OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(completions)),
        environment={"OPENAI_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="usable message content"):
        client.generate(
            GenerationRequest(
                request_id="request-3",
                messages=[ChatMessage(role=MessageRole.USER, content="Hello there")],
                model_name="ignored",
            )
        )


@pytest.mark.parametrize(
    "error_factory",
    [
        FakeRateLimitError,
        FakeResponseRateLimitError,
        lambda: FakeChatRateLimitError("slow down"),
    ],
)
def test_openai_llm_client_retries_rate_limit_errors_with_backoff(
    error_factory: Callable[[], Exception],
) -> None:
    completions = FakeChatCompletionsEndpoint(
        outcomes=[
            error_factory(),
            error_factory(),
            FakeCompletionResponse(
                choices=[FakeChoice(message=FakeChatMessage(content="Recovered"))]
            ),
        ]
    )
    sleep_calls: list[float] = []
    client = OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(completions)),
        sleep=sleep_calls.append,
        environment={"OPENAI_API_KEY": "test-api-key"},
    )

    result = client.generate(
        GenerationRequest(
            request_id="request-4",
            messages=[ChatMessage(role=MessageRole.USER, content="Retry please")],
            model_name="ignored",
        )
    )

    assert sleep_calls == [1.0, 2.0]
    assert len(completions.calls) == 3
    assert result.completion == "Recovered"


def test_openai_llm_client_stops_after_max_rate_limit_attempts() -> None:
    completions = FakeChatCompletionsEndpoint(
        outcomes=[FakeRateLimitError(), FakeRateLimitError(), FakeRateLimitError()]
    )
    sleep_calls: list[float] = []
    client = OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(completions)),
        sleep=sleep_calls.append,
        environment={"OPENAI_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="maximum number of rate-limit"):
        client.generate(
            GenerationRequest(
                request_id="request-5",
                messages=[ChatMessage(role=MessageRole.USER, content="Retry please")],
                model_name="ignored",
            )
        )

    assert sleep_calls == [1.0, 2.0]
    assert len(completions.calls) == 3


def test_openai_llm_client_does_not_retry_non_rate_limit_errors() -> None:
    completions = FakeChatCompletionsEndpoint(outcomes=[RuntimeError("boom")])
    sleep_calls: list[float] = []
    client = OpenAILlmClient(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key_env_var="OPENAI_API_KEY",
        ),
        client=cast(OpenAIClientProtocol, FakeOpenAIClient(completions)),
        sleep=sleep_calls.append,
        environment={"OPENAI_API_KEY": "test-api-key"},
    )

    with pytest.raises(LlmProviderError, match="request failed"):
        client.generate(
            GenerationRequest(
                request_id="request-6",
                messages=[ChatMessage(role=MessageRole.USER, content="Fail fast")],
                model_name="ignored",
            )
        )

    assert sleep_calls == []
    assert len(completions.calls) == 1