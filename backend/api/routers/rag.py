"""RAG chat router exposing conversation read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import ChatConversationResponse
from api.dependencies import (
    get_chat_conversation_create_payload,
    get_chat_conversation_payload,
    get_chat_message_payload,
)

__all__ = ["router"]

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/conversations/{conversation_id}", response_model=ChatConversationResponse)
async def get_conversation(
    conversation: ChatConversationResponse = Depends(get_chat_conversation_payload),
) -> ChatConversationResponse:
    """Return the current conversation state for the RAG assistant."""
    return conversation


@router.post("/conversations", response_model=ChatConversationResponse)
async def create_conversation(
    conversation: ChatConversationResponse = Depends(get_chat_conversation_create_payload),
) -> ChatConversationResponse:
    """Create and return a new conversation."""
    return conversation


@router.post("/conversations/{conversation_id}/messages", response_model=ChatConversationResponse)
async def add_message(
    conversation: ChatConversationResponse = Depends(get_chat_message_payload),
) -> ChatConversationResponse:
    """Append a user message and generated assistant reply to the conversation."""
    return conversation