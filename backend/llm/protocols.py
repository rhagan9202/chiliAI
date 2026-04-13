"""Service-level protocols for the llm module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from llm.service_models import CompletionResponse, GenerateRequest


@runtime_checkable
class LlmServiceProtocol(Protocol):
    """Service boundary for llm generation."""

    def generate(self, request: GenerateRequest) -> CompletionResponse: ...


__all__ = [
    "LlmServiceProtocol",
]