"""Adapter-level protocols for llm clients."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from llm.models import GenerationRequest, GenerationResult


@runtime_checkable
class LlmClientProtocol(Protocol):
    """Generate text completions from normalized llm requests."""

    # TODO(production): Extend with streaming, batch, and token counting methods:
    # - stream_generate(request: GenerationRequest) -> Iterator[str]
    # - count_tokens(request: GenerationRequest) -> int
    # Add tool/function calling support in GenerationRequest.
    # Implement production adapters: OpenAIClient, AnthropicClient, LocalLlmClient.
    # See docs/architecture.md §5 llm module.

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


__all__ = [
    "LlmClientProtocol",
]