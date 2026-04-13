"""Tests for llm module models."""

from __future__ import annotations

import pytest

from llm.models import ChatMessage, GenerationRequest, MessageRole
from llm.service_models import GenerateRequest, PromptTemplate


def test_chat_message_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ChatMessage(role=MessageRole.USER, content="  ")


def test_generation_request_requires_messages() -> None:
    with pytest.raises(ValueError, match="at least one message"):
        GenerationRequest(
            request_id="request-1",
            messages=[],
            model_name="test-model",
        )


def test_generate_request_accepts_prompt_template() -> None:
    request = GenerateRequest(
        prompt_template=PromptTemplate(
            user_prompt="Summarize {topic}",
            variables={"topic": "claims"},
        )
    )

    assert request.prompt_template is not None


def test_generate_request_requires_messages_or_prompt_template() -> None:
    with pytest.raises(ValueError, match="messages or a prompt_template"):
        GenerateRequest()