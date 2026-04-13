"""In-memory llm client adapter for tests and local development."""

from __future__ import annotations

from llm.models import CompletionMetadata, GenerationRequest, GenerationResult, MessageRole

__all__ = ["InMemoryLlmClient"]


class InMemoryLlmClient:
    """A deterministic llm client that echoes the latest user message."""

    # TODO(production): This is a test-only echo stub. Production adapters must:
    # - Make real API calls to LLM providers (OpenAI, Anthropic, etc.)
    # - Implement proper token counting (tiktoken or provider API)
    # - Support streaming responses with SSE
    # - Support tool/function calling with JSON schemas
    # - Handle rate limiting with retry and exponential backoff
    # - Log request/response metrics (latency, token usage, cost)

    def __init__(self, *, provider: str = "in-memory") -> None:
        self._provider = provider

    def generate(self, request: GenerationRequest) -> GenerationResult:
        latest_user_content = next(
            (message.content for message in reversed(request.messages) if message.role is MessageRole.USER),
            None,
        )
        if latest_user_content is None:
            raise ValueError("GenerationRequest must include at least one user message.")
        return GenerationResult(
            request_id=request.request_id,
            completion=f"Echo: {latest_user_content}",
            metadata=CompletionMetadata(
                provider=self._provider,
                model_name=request.model_name,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ),
        )