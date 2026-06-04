"""Internal domain models for durable RAG chat conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from shared.utils import utc_now

ConversationMessageRole = Literal["user", "assistant", "system"]


class ConversationCitation(BaseModel):
    """Provenance for one assistant message, mirroring a RAG citation."""

    record_id: str
    content_id: str
    score: float
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None
    highlight: str | None = None
    entity_id: str | None = None


class ConversationMessage(BaseModel):
    """One message in a durable chat conversation."""

    id: str
    role: ConversationMessageRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    citation_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))
    citations: list[ConversationCitation] = Field(
        default_factory=lambda: cast(list[ConversationCitation], [])
    )


class Conversation(BaseModel):
    """A durable RAG chat conversation and its message history."""

    id: str
    title: str
    knowledge_base_id: str
    messages: list[ConversationMessage] = Field(
        default_factory=lambda: cast(list[ConversationMessage], [])
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "Conversation",
    "ConversationCitation",
    "ConversationMessage",
    "ConversationMessageRole",
]
