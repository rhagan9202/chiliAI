"""Tests for the in-memory llm adapter."""

from __future__ import annotations

import pytest

from llm.adapters.in_memory import InMemoryLlmClient
from llm.models import ChatMessage, GenerationRequest, MessageRole


def test_in_memory_llm_client_echoes_latest_user_message() -> None:
    client = InMemoryLlmClient()

    result = client.generate(
        GenerationRequest(
            request_id="request-1",
            messages=[
                ChatMessage(role=MessageRole.SYSTEM, content="You are concise."),
                ChatMessage(role=MessageRole.USER, content="Summarize findings"),
            ],
            model_name="test-model",
        )
    )

    assert result.completion == "Echo: Summarize findings"
    assert result.metadata.provider == "in-memory"


def test_in_memory_llm_client_requires_user_message() -> None:
    client = InMemoryLlmClient()

    with pytest.raises(ValueError, match="user message"):
        client.generate(
            GenerationRequest(
                request_id="request-1",
                messages=[ChatMessage(role=MessageRole.SYSTEM, content="Only system")],
                model_name="test-model",
            )
        )