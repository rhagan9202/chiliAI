"""RAG chat router exposing conversation read models and streaming responses.

Owns POST/GET on ``/chat/conversations[/...]``. The non-streaming path returns
the full conversation read model after appending the user message and the
generated assistant reply. With ``?stream=true`` the same endpoint streams
SSE token chunks instead, terminated by a ``done`` sentinel that carries the
final source citations.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.contracts import ChatConversationResponse, ChatMessageCreateRequest
from api.dependencies import (
    get_api_state,
    get_chat_conversation_create_payload,
    get_chat_conversation_payload,
)
from api.middleware.rbac import require_role
from api.state import ApiState
from rag.exceptions import RagConfigurationError
from rag.protocols import RagServiceProtocol
from rag.service_models import RagQueryRequest, RagStreamChunk

__all__ = ["router"]

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get(
    "/conversations/{conversation_id}",
    response_model=ChatConversationResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_conversation(
    conversation: ChatConversationResponse = Depends(get_chat_conversation_payload),
) -> ChatConversationResponse:
    """Return the current conversation state for the RAG assistant."""
    return conversation


@router.post(
    "/conversations",
    response_model=ChatConversationResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def create_conversation(
    conversation: ChatConversationResponse = Depends(get_chat_conversation_create_payload),
) -> ChatConversationResponse:
    """Create and return a new conversation."""
    return conversation


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=None,
    dependencies=[Depends(require_role("viewer"))],
)
async def add_message(
    conversation_id: str,
    payload: ChatMessageCreateRequest,
    stream: bool = False,
    state: ApiState = Depends(get_api_state),
) -> Union[ChatConversationResponse, StreamingResponse]:
    """Append a message to a conversation; stream tokens with ``?stream=true``."""

    if not stream:
        try:
            return state.add_message(conversation_id, payload)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation '{conversation_id}' not found.",
            ) from exc

    try:
        conversation = state.get_conversation(conversation_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found.",
        ) from exc

    return StreamingResponse(
        _stream_sse(
            state.rag_service,
            knowledge_base_id=conversation.knowledge_base_id,
            question=payload.content,
        ),
        media_type="text/event-stream",
    )


async def _stream_sse(
    rag_service: RagServiceProtocol,
    *,
    knowledge_base_id: str,
    question: str,
) -> AsyncIterator[bytes]:
    query_request = RagQueryRequest(
        knowledge_base_id=knowledge_base_id,
        question=question,
    )
    try:
        for chunk in rag_service.stream_answer(query_request):
            yield _sse_event(_chunk_to_payload(chunk))
    except RagConfigurationError as exc:
        yield _sse_event({"error": str(exc), "done": True})


def _chunk_to_payload(chunk: RagStreamChunk) -> dict[str, object]:
    payload: dict[str, object] = {"token": chunk.chunk_text, "done": chunk.is_final}
    if chunk.is_final:
        payload["sources"] = [citation.record_id for citation in chunk.citations]
    return payload


def _sse_event(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
