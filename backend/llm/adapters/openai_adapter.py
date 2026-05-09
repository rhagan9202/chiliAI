"""OpenAI chat completions adapter for the llm module."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import importlib
import os
import time
from typing import Protocol, TypedDict, cast

from config.schema import LlmConfig
from llm.exceptions import LlmConfigurationError, LlmProviderError
from llm.models import CompletionMetadata, GenerationRequest, GenerationResult

__all__ = ["OpenAIClientProtocol", "OpenAILlmClient"]

_MAX_RETRY_ATTEMPTS = 3
_PROVIDER_NAME = "openai"


class OpenAIMessageParam(TypedDict):
    """Minimal request shape accepted by the OpenAI chat endpoint."""

    role: str
    content: str


class OpenAIChatCompletionsProtocol(Protocol):
    """Structural boundary for the OpenAI chat completions endpoint."""

    def create(
        self,
        *,
        model: str,
        messages: Sequence[OpenAIMessageParam],
        temperature: float,
        max_tokens: int,
    ) -> object: ...


class OpenAIChatProtocol(Protocol):
    """Structural boundary for the OpenAI chat API surface."""

    completions: OpenAIChatCompletionsProtocol


class OpenAIClientProtocol(Protocol):
    """Structural boundary for the OpenAI client used by this adapter."""

    chat: OpenAIChatProtocol


class OpenAILlmClient:
    """Generate LLM completions with the OpenAI Chat Completions API."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        client: OpenAIClientProtocol | None = None,
        client_factory: Callable[[str], OpenAIClientProtocol] | None = None,
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
            else (client_factory or _create_openai_client)(api_key)
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate a single completion for a normalized request."""

        response = self._create_completion_with_retry(request)
        completion = _parse_completion(response)
        prompt_tokens = _read_usage_tokens(response, field_name="prompt_tokens")
        completion_tokens = _read_usage_tokens(
            response,
            field_name="completion_tokens",
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

    def _create_completion_with_retry(self, request: GenerationRequest) -> object:
        """Call the provider with retry for transient rate-limit failures."""

        messages = _build_messages(request)
        attempt = 1
        while True:
            try:
                return self._client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise LlmProviderError(
                        "OpenAI chat completion request failed."
                    ) from exc

                if attempt >= _MAX_RETRY_ATTEMPTS:
                    raise LlmProviderError(
                        "OpenAI chat completion request exceeded the maximum "
                        "number of rate-limit retry attempts."
                    ) from exc

                self._sleep(float(2 ** (attempt - 1)))
                attempt += 1


def _validate_api_key_env_var(api_key_env_var: str | None) -> str:
    """Validate that a usable API key env var is configured."""

    if api_key_env_var is None or api_key_env_var.strip() == "":
        raise LlmConfigurationError(
            "LlmConfig.api_key_env_var must be configured for the OpenAI "
            "LLM adapter."
        )
    return api_key_env_var


def _read_api_key(api_key_env_var: str, *, environment: Mapping[str, str]) -> str:
    """Read and validate the configured API key from the environment."""

    api_key = environment.get(api_key_env_var)
    if api_key is None or api_key.strip() == "":
        raise LlmConfigurationError(
            "OpenAI API key is missing. Set the environment variable "
            f"'{api_key_env_var}'."
        )
    return api_key


def _create_openai_client(api_key: str) -> OpenAIClientProtocol:
    """Create the OpenAI SDK client only when the adapter is constructed."""

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


def _build_messages(request: GenerationRequest) -> list[OpenAIMessageParam]:
    """Convert normalized chat messages into the provider request shape."""

    return [
        OpenAIMessageParam(role=message.role.value, content=message.content)
        for message in request.messages
    ]


def _parse_completion(response: object) -> str:
    """Extract the first completion message content from a provider response."""

    choices_object = getattr(response, "choices", None)
    if not isinstance(choices_object, Sequence) or isinstance(
        choices_object, str | bytes
    ):
        raise LlmProviderError(
            "OpenAI chat completion response did not include a usable choices "
            "sequence."
        )

    choices = list(cast(Sequence[object], choices_object))
    if not choices:
        raise LlmProviderError(
            "OpenAI chat completion response did not include any choices."
        )

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str) or content.strip() == "":
        raise LlmProviderError(
            "OpenAI chat completion response did not include a usable message "
            "content string."
        )
    return content


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
            "OpenAI chat completion usage metadata contained an invalid "
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