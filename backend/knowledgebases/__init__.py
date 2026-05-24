"""Knowledge base and document metadata persistence.

Used by `api/` (gateway routers) and `agent/` (worker coordinator). Lives
outside both so neither feature module needs to import from the other,
honoring CLAUDE.md Hard Rule 1.
"""

from __future__ import annotations

from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from knowledgebases.protocols import KnowledgeBaseRepository

__all__ = [
    "DocumentRecord",
    "InMemoryKnowledgeBaseRepository",
    "KnowledgeBaseRepository",
    "ObjectStoreKnowledgeBaseRepository",
]
