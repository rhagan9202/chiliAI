"""Models for the knowledgebases module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.utils import utc_now

__all__ = ["DocumentRecord"]


class DocumentRecord(BaseModel):
    """Metadata recorded for a registered document inside a knowledge base."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str = "registered"
    storage_key: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
