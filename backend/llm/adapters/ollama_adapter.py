"""LLM client adapter for a local Ollama HTTP endpoint."""

from __future__ import annotations

import httpx

from llm.exceptions import LlmProviderError
from llm.models import CompletionMetadata, GenerationRequest, GenerationResult


class OllamaLlmClient:
    """Generate completions against an Ollama HTTP API.

    Implements the `LlmClientProtocol`. Reads `base_url` from constructor (the
    factory passes it from `LlmConfig.base_url`).
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = {
            "model": request.model_name,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LlmProviderError(f"Ollama transport error: {exc}") from exc

        if response.status_code >= 500:
            raise LlmProviderError(
                f"Ollama returned {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise LlmProviderError(
                f"Ollama rejected request ({response.status_code}): {response.text[:200]}"
            )

        body = response.json()
        completion = body.get("message", {}).get("content", "")
        if not completion.strip():
            raise LlmProviderError("Ollama returned an empty completion.")

        return GenerationResult(
            request_id=request.request_id,
            completion=completion,
            metadata=CompletionMetadata(
                provider="ollama",
                model_name=request.model_name,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ),
        )

    def close(self) -> None:
        self._client.close()


__all__ = ["OllamaLlmClient"]
