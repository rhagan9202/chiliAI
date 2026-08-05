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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from knowledgebases.protocols import KnowledgeBaseRepository
from api.contracts import (
    ChatConversationListResponse,
    ChatConversationResponse,
    ChatMessageCreateRequest,
)
from api.dependencies import (
    get_api_state,
    get_chat_conversation_create_payload,
    get_chat_conversation_list_payload,
    get_chat_conversation_payload,
    get_chat_message_payload,
    get_conversation_service,
    get_domain_config,
    get_knowledge_base_repository,
    require_kb_scoped_conversation,
)
from api.middleware.rbac import require_role
from api.state import ApiState
from conversations.service import ConversationService
from config.schema import DomainConfig, ValidationConfig
from rag.exceptions import RagConfigurationError
from rag.protocols import RagServiceProtocol
from rag.service_models import RagQueryRequest, RagStreamChunk
from shared.kb_scope import resolve_kb_scope
from shared.validation import validate_query_length

__all__ = ["router"]

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get(
    "/conversations",
    response_model=ChatConversationListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_conversations(
    conversations: ChatConversationListResponse = Depends(get_chat_conversation_list_payload),
) -> ChatConversationListResponse:
    """Return the active knowledge base's conversations, newest activity first."""
    return conversations


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
    response_model=ChatConversationResponse,
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "description": "Server-sent events carrying token chunks and a final citation event.",
                },
            }
        }
    },
    dependencies=[Depends(require_role("analyst"))],
)
async def add_message(
    conversation_id: str,
    payload: ChatMessageCreateRequest,
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base identifier."
    ),
    stream: bool = False,
    state: ApiState = Depends(get_api_state),
    domain_config: DomainConfig = Depends(get_domain_config),
    conversation_service: ConversationService = Depends(get_conversation_service),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
) -> Union[ChatConversationResponse, StreamingResponse]:
    """Append a message to a conversation; stream tokens with ``?stream=true``."""

    validation = domain_config.validation or ValidationConfig()
    try:
        cleaned_content = validate_query_length(
            payload.content,
            validation.max_rag_question_length,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    payload = payload.model_copy(update={"content": cleaned_content})

    if not stream:
        # Non-streaming append + persistence is owned by the durable-repo
        # dependency, which 404s on an unknown id or one outside this KB.
        # `knowledge_base_id` is threaded through explicitly because this is a
        # direct call, not a `Depends` — FastAPI does not resolve the
        # dependency's own query parameters on this path.
        return get_chat_message_payload(
            payload,
            conversation_id=conversation_id,
            knowledge_base_id=knowledge_base_id,
            state=state,
            service=conversation_service,
            config=domain_config,
        )

    # The streaming branch reads the conversation itself, so it needs the same
    # KB guard: without it, retrieval could be driven over a knowledge base the
    # caller never named.
    conversation = require_kb_scoped_conversation(
        conversation_service, conversation_id, knowledge_base_id
    )

    kb_ids = resolve_kb_scope(conversation.knowledge_base_id, domain_config, kb_repository)
    return StreamingResponse(
        _stream_sse(
            state.rag_service,
            knowledge_base_ids=kb_ids,
            question=payload.content,
            include_graph_context=payload.include_graph_context,
            filters=payload.filters,
        ),
        media_type="text/event-stream",
    )


async def _stream_sse(
    rag_service: RagServiceProtocol,
    *,
    knowledge_base_ids: list[str],
    question: str,
    include_graph_context: bool,
    filters: dict[str, str | int | float | bool],
) -> AsyncIterator[bytes]:
    query_request = RagQueryRequest(
        knowledge_base_ids=knowledge_base_ids,
        question=question,
        include_graph_context=include_graph_context,
        filters=filters,
    )
    try:
        for chunk in rag_service.stream_answer(query_request):
            yield _sse_event(_chunk_to_payload(chunk))
    except RagConfigurationError as exc:
        yield _sse_event({"error": str(exc), "done": True})


def _chunk_to_payload(chunk: RagStreamChunk) -> dict[str, object]:
    payload: dict[str, object] = {"token": chunk.chunk_text, "done": chunk.is_final}
    if chunk.is_final:
        # Legacy field: list of record_ids for backwards compatibility with older clients.
        payload["sources"] = [citation.record_id for citation in chunk.citations]
        # BL-002: rich citation payload so the chat UI can render snippet,
        # document anchor, score, and (when available) entity click-through.
        payload["citations"] = [
            {
                "record_id": citation.record_id,
                "content_id": citation.content_id,
                "score": citation.score,
                "snippet": citation.snippet,
                "document_id": citation.document_id,
                "chunk_index": citation.chunk_index,
                "highlight": citation.highlight,
                "entity_id": None,
            }
            for citation in chunk.citations
        ]
    return payload


def _sse_event(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
