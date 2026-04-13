"""LLM adapters."""

from __future__ import annotations

from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.protocols import LlmClientProtocol

__all__ = ["InMemoryLlmClient", "LlmClientProtocol"]