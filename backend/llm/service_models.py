"""API-boundary models for llm requests and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from llm.models import MessageRole


PromptVariableValue = str | int | float | bool


def _default_chat_message_inputs() -> list[ChatMessageInput]:
    """Return a typed empty chat-message list for strict type checking."""

    return []


class ChatMessageInput(BaseModel):
    """A chat message supplied by API or worker callers."""

    role: MessageRole
    content: str

    @model_validator(mode="after")
    def _validate_content(self) -> ChatMessageInput:
        if self.content.strip() == "":
            raise ValueError("ChatMessageInput content must not be empty.")
        return self


class PromptTemplate(BaseModel):
    """A prompt template that may be rendered with named variables."""

    system_prompt: str | None = None
    user_prompt: str
    variables: dict[str, PromptVariableValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_prompt(self) -> PromptTemplate:
        if self.user_prompt.strip() == "":
            raise ValueError("PromptTemplate user_prompt must not be empty.")
        return self


class GenerateRequest(BaseModel):
    """Service-boundary generation request."""

    knowledge_base_id: str | None = None
    model_name: str = "in-memory-test-model"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, gt=0)
    messages: list[ChatMessageInput] = Field(
        default_factory=_default_chat_message_inputs
    )
    prompt_template: PromptTemplate | None = None

    @model_validator(mode="after")
    def _validate_payload(self) -> GenerateRequest:
        if self.messages or self.prompt_template is not None:
            return self
        raise ValueError("GenerateRequest requires messages or a prompt_template.")


class CompletionResponse(BaseModel):
    """Service-boundary completion response."""

    request_id: str
    completion: str
    provider: str
    model_name: str


__all__ = [
    "ChatMessageInput",
    "CompletionResponse",
    "GenerateRequest",
    "PromptTemplate",
    "PromptVariableValue",
]