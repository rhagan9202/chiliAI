"""Anthropic Messages API adapter for the llm module."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import importlib
import os
import time
from typing import Protocol, TypedDict, cast

from config.schema import LlmConfig
from llm.exceptions import LlmConfigurationError, LlmProviderError
from llm.models import (
    CompletionMetadata,
    GenerationRequest,
    GenerationResult,
    MessageRole,
)

__all__ = ["AnthropicClientProtocol", "AnthropicLlmClient"]

_MAX_RETRY_ATTEMPTS = 3
_PROVIDER_NAME = "anthropic"


class AnthropicMessageParam(TypedDict):
    """Minimal message shape accepted by the Anthropic Messages API."""

    role: str
    content: str


class AnthropicMessagesProtocol(Protocol):
    """Structural boundary for the Anthropic messages endpoint."""

    def create(
        self,
        *,
        model: str,
        messages: Sequence[AnthropicMessageParam],
        temperature: float,
        max_tokens: int,
        system: str | None = None,
    ) -> object: ...


class AnthropicClientProtocol(Protocol):
    """Structural boundary for the Anthropic client used by this adapter."""

    messages: AnthropicMessagesProtocol


class AnthropicLlmClient:
    """Generate LLM completions with the Anthropic Messages API."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        client: AnthropicClientProtocol | None = None,
        client_factory: Callable[[str], AnthropicClientProtocol] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        environment: Mapping[str, str] | None = None,
    ) -> None:
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
            else (client_factory or _create_anthropic_client)(api_key)
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate a single completion for a normalized request."""

        response = self._create_message_with_retry(request)
        completion = _parse_completion(response)
        prompt_tokens = _read_usage_tokens(response, field_name="input_tokens")
        completion_tokens = _read_usage_tokens(
            response,
            field_name="output_tokens",
        )

        return GenerationResult(
            request_id=request.request_id,
            completion=completion,
            metadata=CompletionMetadata(
                provider=_PROVIDER_NAME,
                model_name=self._model_name,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )

    def _create_message_with_retry(self, request: GenerationRequest) -> object:
        """Call the provider with retry for transient rate-limit failures."""

        messages = _build_messages(request)
        system_prompt = _build_system_prompt(request)
        attempt = 1
        while True:
            try:
                return self._client.messages.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    system=system_prompt,
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise LlmProviderError(
                        "Anthropic messages request failed."
                    ) from exc

                if attempt >= _MAX_RETRY_ATTEMPTS:
                    raise LlmProviderError(
                        "Anthropic messages request exceeded the maximum "
                        "number of rate-limit retry attempts."
                    ) from exc

                self._sleep(float(2 ** (attempt - 1)))
                attempt += 1


def _validate_api_key_env_var(api_key_env_var: str | None) -> str:
    """Validate that a usable API key env var is configured."""

    if api_key_env_var is None or api_key_env_var.strip() == "":
        raise LlmConfigurationError(
            "LlmConfig.api_key_env_var must be configured for the Anthropic "
            "LLM adapter."
        )
    return api_key_env_var


def _read_api_key(api_key_env_var: str, *, environment: Mapping[str, str]) -> str:
    """Read and validate the configured API key from the environment."""

    api_key = environment.get(api_key_env_var)
    if api_key is None or api_key.strip() == "":
        raise LlmConfigurationError(
            "Anthropic API key is missing. Set the environment variable "
            f"'{api_key_env_var}'."
        )
    return api_key


def _create_anthropic_client(api_key: str) -> AnthropicClientProtocol:
    """Create the Anthropic SDK client only when the adapter is constructed."""

    try:
        anthropic_module = importlib.import_module("anthropic")
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "The optional anthropic dependency is not installed. Install "
            "chili-backend[anthropic]."
        ) from exc

    constructor_object = getattr(anthropic_module, "Anthropic", None)
    if constructor_object is None or not callable(constructor_object):
        raise ImportError(
            "anthropic is installed, but Anthropic could not be imported."
        )

    constructor = cast(Callable[..., AnthropicClientProtocol], constructor_object)
    return constructor(api_key=api_key)


def _build_system_prompt(request: GenerationRequest) -> str | None:
    """Join normalized system messages into Anthropic's top-level system prompt."""

    system_parts = [
        message.content
        for message in request.messages
        if message.role is MessageRole.SYSTEM
    ]
    if not system_parts:
        return None
    return "\n\n".join(system_parts)


def _build_messages(request: GenerationRequest) -> list[AnthropicMessageParam]:
    """Convert normalized chat messages into Anthropic message parameters."""

    messages = [
        AnthropicMessageParam(role=message.role.value, content=message.content)
        for message in request.messages
        if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
    ]
    if not messages:
        raise LlmProviderError(
            "Anthropic messages requests require at least one non-system "
            "message."
        )
    return messages


def _parse_completion(response: object) -> str:
    """Extract concatenated text blocks from an Anthropic response."""

    content_object = getattr(response, "content", None)
    if not isinstance(content_object, Sequence) or isinstance(
        content_object, str | bytes
    ):
        raise LlmProviderError(
            "Anthropic messages response did not include a usable content "
            "sequence."
        )

    blocks = list(cast(Sequence[object], content_object))
    if not blocks:
        raise LlmProviderError(
            "Anthropic messages response did not include any content blocks."
        )

    text_parts = [
        text
        for block in blocks
        if isinstance((text := getattr(block, "text", None)), str)
        and text.strip() != ""
    ]
    if not text_parts:
        raise LlmProviderError(
            "Anthropic messages response did not include usable text "
            "content."
        )
    return "".join(text_parts)


def _read_usage_tokens(response: object, *, field_name: str) -> int | None:
    """Read an optional non-negative usage token value from the response."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    raw_value = getattr(usage, field_name, None)
    if raw_value is None:
        return None
    if not isinstance(raw_value, int) or raw_value < 0:
        raise LlmProviderError(
            "Anthropic messages usage metadata contained an invalid "
            f"'{field_name}' value."
        )
    return raw_value


def _is_rate_limit_error(error: Exception) -> bool:
    """Detect rate-limit failures without importing SDK-specific types."""

    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if response_status == 429:
        return True

    return "ratelimit" in type(error).__name__.lower()