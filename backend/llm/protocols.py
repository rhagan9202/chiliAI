"""Service-level protocols for the llm module."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from llm.service_models import CompletionResponse, GenerateRequest


@runtime_checkable
class LlmServiceProtocol(Protocol):
    """Service boundary for llm generation."""

    def generate(self, request: GenerateRequest) -> CompletionResponse: ...

    def generate_stream(
        self,
        request: GenerateRequest,
    ) -> AsyncIterator[str]:
        """Stream completion chunks for `request`.

        Implementations may provide provider-native token streaming or a
        production-safe fallback that yields a one-shot completion chunk.
        """

        raise NotImplementedError(
            "generate_stream is not implemented by this llm adapter."
        )


__all__ = [
    "LlmServiceProtocol",
]
