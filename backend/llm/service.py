"""Service entry point for llm generation flows."""

from __future__ import annotations

from collections.abc import AsyncIterator

from events.protocols import EventBus
from events.types import LlmCompletedEvent, LlmCompletionReference
from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmConfigurationError, LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole
from llm.service_models import CompletionResponse, GenerateRequest, PromptTemplate
from shared.utils import generate_id


class LlmService:
    """Coordinate request rendering, client invocation, and event publication."""

    # TODO(production): Add retry logic with exponential backoff for provider errors
    # and rate limits. Add provider-native token streaming once adapters expose
    # stream_generate. Add pre-flight token budget checking. Add model capability
    # registry to select models by feature (vision, tool use, context length).
    # Add fallback model support: if primary model fails, try a configured
    # secondary.

    def __init__(self, client: LlmClientProtocol, *, event_bus: EventBus) -> None:
        self._client = client
        self._event_bus = event_bus

    def generate(self, request: GenerateRequest) -> CompletionResponse:
        messages = _build_messages(request)
        generation_request = GenerationRequest(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            messages=messages,
            model_name=request.model_name,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        try:
            result = self._client.generate(generation_request)
        except ValueError as exc:
            raise LlmConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise LlmProviderError("Failed to generate llm completion.") from exc

        response = CompletionResponse(
            request_id=result.request_id,
            completion=result.completion,
            provider=result.metadata.provider,
            model_name=result.metadata.model_name,
        )
        self._event_bus.publish(
            LlmCompletedEvent(
                completions=[
                    LlmCompletionReference(
                        knowledge_base_id=request.knowledge_base_id,
                        request_id=response.request_id,
                        model_name=response.model_name,
                        provider=response.provider,
                        message_count=len(messages),
                        completion_length=len(response.completion),
                    )
                ]
            )
        )
        return response

    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        """Stream a completion for ``request``.

        The default service provides a production-safe fallback by delegating to
        :meth:`generate` and yielding the full completion as a single chunk.
        Provider-native token streaming can be added by future adapters without
        requiring callers to guard this method.
        """

        response = self.generate(request)
        yield response.completion


def create_llm_service(client: LlmClientProtocol, *, event_bus: EventBus) -> LlmService:
    """Create the default llm service."""

    return LlmService(client, event_bus=event_bus)


def _build_messages(request: GenerateRequest) -> list[ChatMessage]:
    if request.messages:
        return [ChatMessage(role=message.role, content=message.content) for message in request.messages]
    if request.prompt_template is None:
        raise LlmConfigurationError("GenerateRequest requires messages or prompt_template.")
    return _render_prompt_template(request.prompt_template)


def _render_prompt_template(prompt_template: PromptTemplate) -> list[ChatMessage]:
    rendered_system = (
        prompt_template.system_prompt.format(**prompt_template.variables)
        if prompt_template.system_prompt is not None
        else None
    )
    rendered_user = prompt_template.user_prompt.format(**prompt_template.variables)
    messages: list[ChatMessage] = []
    if rendered_system is not None:
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=rendered_system))
    messages.append(ChatMessage(role=MessageRole.USER, content=rendered_user))
    return messages


__all__ = ["LlmService", "create_llm_service"]