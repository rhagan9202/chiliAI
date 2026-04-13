"""Internal transport and workflow models for llm interactions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, Enum):
    """Supported roles for chat-style llm requests."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """A normalized message passed to an llm client."""

    role: MessageRole
    content: str

    @model_validator(mode="after")
    def _validate_content(self) -> ChatMessage:
        if self.content.strip() == "":
            raise ValueError("ChatMessage content must not be empty.")
        return self


class CompletionMetadata(BaseModel):
    """Metadata returned alongside a completion result."""

    provider: str
    model_name: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(gt=0)
    created_at: datetime = Field(default_factory=_utc_now)


class GenerationRequest(BaseModel):
    """Internal llm generation request passed to an llm adapter."""

    request_id: str
    knowledge_base_id: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    model_name: str
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, gt=0)

    @model_validator(mode="after")
    def _validate_messages(self) -> GenerationRequest:
        if not self.messages:
            raise ValueError("GenerationRequest requires at least one message.")
        return self


class GenerationResult(BaseModel):
    """Internal llm generation result returned by an llm adapter."""

    request_id: str
    completion: str
    metadata: CompletionMetadata

    @model_validator(mode="after")
    def _validate_completion(self) -> GenerationResult:
        if self.completion.strip() == "":
            raise ValueError("GenerationResult completion must not be empty.")
        return self


__all__ = [
    "ChatMessage",
    "CompletionMetadata",
    "GenerationRequest",
    "GenerationResult",
    "MessageRole",
]