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
        """Stream tokens for `request`.

        Optional: implementations that do not support streaming should raise
        ``NotImplementedError``. The default implementation here raises so
        that adapter authors must opt in.
        """

        raise NotImplementedError(
            "generate_stream is not implemented by this llm adapter."
        )


__all__ = [
    "LlmServiceProtocol",
]
