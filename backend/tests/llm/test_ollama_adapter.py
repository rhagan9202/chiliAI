from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from llm.adapters.ollama_adapter import OllamaLlmClient
from llm.exceptions import LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole


def _request() -> GenerationRequest:
    return GenerationRequest(
        request_id="r1",
        model_name="llama3.1:8b",
        messages=[ChatMessage(role=MessageRole.USER, content="hello")],
    )


def test_generate_calls_ollama_chat_endpoint() -> None:
    response = httpx.Response(
        status_code=200,
        json={"message": {"content": "hi there"}, "done": True},
    )
    with patch.object(httpx.Client, "post", return_value=response) as post:
        client = OllamaLlmClient(base_url="http://localhost:11434")
        result = client.generate(_request())

    assert result.completion == "hi there"
    assert result.metadata.provider == "ollama"
    assert result.metadata.model_name == "llama3.1:8b"
    args, kwargs = post.call_args
    assert args[0].endswith("/api/chat")
    assert kwargs["json"]["model"] == "llama3.1:8b"


def test_generate_raises_on_5xx() -> None:
    response = httpx.Response(status_code=503, text="overloaded")
    with patch.object(httpx.Client, "post", return_value=response):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())


def test_generate_raises_on_4xx() -> None:
    response = httpx.Response(status_code=404, text="model not found")
    with patch.object(httpx.Client, "post", return_value=response):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())


def test_generate_raises_on_empty_completion() -> None:
    response = httpx.Response(
        status_code=200,
        json={"message": {"content": ""}, "done": True},
    )
    with patch.object(httpx.Client, "post", return_value=response):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())


def test_generate_raises_on_transport_error() -> None:
    def raise_transport(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("connection refused")

    with patch.object(httpx.Client, "post", side_effect=raise_transport):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())
