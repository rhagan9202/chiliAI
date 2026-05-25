"""Public exports for the llm service module."""

from __future__ import annotations

from llm.adapters.anthropic_adapter import AnthropicLlmClient
from llm.adapters.fallback import FallbackLlmClient
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.ollama_adapter import OllamaLlmClient
from llm.adapters.openai_adapter import OpenAILlmClient
from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmConfigurationError, LlmError, LlmProviderError
from llm.factory import create_llm_client
from llm.models import ChatMessage, CompletionMetadata, GenerationRequest, GenerationResult, MessageRole
from llm.protocols import LlmServiceProtocol
from llm.service import LlmService, create_llm_service
from llm.service_models import (
    ChatMessageInput,
    CompletionResponse,
    GenerateRequest,
    PromptTemplate,
)

__all__ = [
    "AnthropicLlmClient",
    "ChatMessage",
    "ChatMessageInput",
    "CompletionMetadata",
    "CompletionResponse",
    "FallbackLlmClient",
    "GenerateRequest",
    "GenerationRequest",
    "GenerationResult",
    "InMemoryLlmClient",
    "LlmClientProtocol",
    "LlmConfigurationError",
    "LlmError",
    "LlmProviderError",
    "LlmService",
    "LlmServiceProtocol",
    "MessageRole",
    "OllamaLlmClient",
    "OpenAILlmClient",
    "PromptTemplate",
    "create_llm_client",
    "create_llm_service",
]