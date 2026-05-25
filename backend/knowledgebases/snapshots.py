"""Internal serialization snapshot for object-store-backed persistence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from knowledgebases.models import DocumentRecord
from shared.types import KnowledgeBase

__all__ = ["KnowledgeBaseStoreSnapshot"]


class KnowledgeBaseStoreSnapshot(BaseModel):
    """Serialized repository state for durable object-store persistence."""

    knowledge_bases: dict[str, KnowledgeBase] = Field(default_factory=dict)
    knowledge_base_order: list[str] = Field(default_factory=list)
    documents: dict[str, dict[str, DocumentRecord]] = Field(default_factory=dict)
    document_order: dict[str, list[str]] = Field(default_factory=dict)
