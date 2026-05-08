"""RAG chat API endpoints — send and stream messages."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from api.middleware.rbac import require_role
from rag.adapters.in_memory import InMemoryRagService
from rag.exceptions import RagConfigurationError
from rag.protocols import RagServiceProtocol
from rag.service_models import RagQueryRequest, RagStreamChunk

__all__ = [
    "ChatMessageRequest",
    "ChatMessageResponse",
    "get_rag_service",
    "router",
]


# NOTE: This factory is intentionally local to the chat router. The shared
# `api.dependencies` module is owned by other stories; tests override this
# factory through `app.dependency_overrides[get_rag_service]`.
@lru_cache(maxsize=1)
def get_rag_service() -> RagServiceProtocol:
    """Return the rag service implementation backing the chat router."""

    return InMemoryRagService()


class ChatMessageRequest(BaseModel):
    """Inbound chat message payload."""

    content: str
    kb_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_content(self) -> ChatMessageRequest:
        if self.content.strip() == "":
            raise ValueError("ChatMessageRequest content must not be empty.")
        return self


class ChatMessageResponse(BaseModel):
    """Outbound chat message payload."""

    content: str
    sources: list[str] = Field(default_factory=list)


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=None,
    dependencies=[Depends(require_role("viewer"))],
)
async def send_chat_message(
    conversation_id: str,
    request: ChatMessageRequest,
    stream: bool = False,
    rag_service: RagServiceProtocol = Depends(get_rag_service),
) -> ChatMessageResponse | StreamingResponse:
    """Send a chat message and return either a single response or an SSE stream."""

    del conversation_id  # Reserved for future conversation threading.
    if request.content.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content must not be empty.",
        )

    if stream:
        return StreamingResponse(
            _stream_sse(rag_service, knowledge_base_id=request.kb_id, question=request.content),
            media_type="text/event-stream",
        )

    try:
        answer = rag_service.answer_question(
            knowledge_base_id=request.kb_id,
            question=request.content,
        )
    except RagConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ChatMessageResponse(content=answer.content, sources=list(answer.sources))


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
