"""Adapter-level protocols for llm clients."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from llm.models import GenerationRequest, GenerationResult


@runtime_checkable
class LlmClientProtocol(Protocol):
    """Generate text completions from normalized llm requests."""

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


__all__ = [
    "LlmClientProtocol",
]