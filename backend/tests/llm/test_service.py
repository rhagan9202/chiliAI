"""Tests for the llm service."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import LlmCompletedEvent
from llm.adapters.in_memory import InMemoryLlmClient
from llm.models import MessageRole
from llm.service import create_llm_service
from llm.service_models import ChatMessageInput, GenerateRequest, PromptTemplate


def test_llm_service_generates_from_messages_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_llm_service(InMemoryLlmClient(), event_bus=event_bus)

    response = service.generate(
        GenerateRequest(
            knowledge_base_id="kb-1",
            messages=[ChatMessageInput(role=MessageRole.USER, content="Explain claim 42")],
        )
    )

    assert response.completion == "Echo: Explain claim 42"
    assert isinstance(event_bus.published_events[-1], LlmCompletedEvent)


def test_llm_service_renders_prompt_template() -> None:
    event_bus = InMemoryEventBus()
    service = create_llm_service(InMemoryLlmClient(), event_bus=event_bus)

    response = service.generate(
        GenerateRequest(
            prompt_template=PromptTemplate(
                system_prompt="You are a concise analyst.",
                user_prompt="Summarize {topic}",
                variables={"topic": "provider risk"},
            )
        )
    )

    assert response.completion == "Echo: Summarize provider risk"