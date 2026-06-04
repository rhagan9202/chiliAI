"""API-layer projection + RAG glue for durable chat conversations (BL-012).

The :mod:`conversations` module owns persistence and is contract-agnostic. This
module adapts its domain models to the frontend ``Chat*`` contracts and builds
the user/assistant message pair from a RAG answer, so routers and the
``get_chat_*`` dependencies stay thin.
"""

from __future__ import annotations

from api.contracts import (
    ChatCitationResponse,
    ChatConversationResponse,
    ChatMessageResponse,
)
from conversations.models import (
    Conversation,
    ConversationCitation,
    ConversationMessage,
)
from rag.service_models import RagQueryResponse
from shared.utils import generate_id, utc_now

__all__ = [
    "build_assistant_message",
    "build_user_message",
    "project_conversation",
]


def project_conversation(conversation: Conversation) -> ChatConversationResponse:
    """Project a durable conversation onto the frontend chat contract."""
    return ChatConversationResponse(
        id=conversation.id,
        title=conversation.title,
        knowledge_base_id=conversation.knowledge_base_id,
        messages=[_project_message(message) for message in conversation.messages],
    )


def build_user_message(content: str) -> ConversationMessage:
    """Return a freshly-stamped user message for persistence."""
    return ConversationMessage(
        id=generate_id(),
        role="user",
        content=content,
        created_at=utc_now(),
    )


def build_assistant_message(rag_response: RagQueryResponse) -> ConversationMessage:
    """Return an assistant message carrying the RAG answer + citations."""
    return ConversationMessage(
        id=generate_id(),
        role="assistant",
        content=rag_response.answer,
        created_at=utc_now(),
        citation_ids=[citation.content_id for citation in rag_response.citations],
        citations=[
            ConversationCitation(
                record_id=citation.record_id,
                content_id=citation.content_id,
                score=citation.score,
                snippet=citation.snippet,
                document_id=citation.document_id,
                chunk_index=citation.chunk_index,
                highlight=citation.highlight,
            )
            for citation in rag_response.citations
        ],
    )


def _project_message(message: ConversationMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citation_ids=list(message.citation_ids),
        citations=[_project_citation(citation) for citation in message.citations],
    )


def _project_citation(citation: ConversationCitation) -> ChatCitationResponse:
    return ChatCitationResponse(
        record_id=citation.record_id,
        content_id=citation.content_id,
        score=citation.score,
        snippet=citation.snippet,
        document_id=citation.document_id,
        chunk_index=citation.chunk_index,
        highlight=citation.highlight,
        entity_id=citation.entity_id,
    )
