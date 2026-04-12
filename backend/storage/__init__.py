"""Object storage contracts and in-memory adapter."""

from storage.adapters.in_memory import InMemoryObjectStore
from storage.models import StoredObject, StoredObjectWriteResult
from storage.protocols import ObjectStore

__all__ = [
    "InMemoryObjectStore",
    "ObjectStore",
    "StoredObject",
    "StoredObjectWriteResult",
]