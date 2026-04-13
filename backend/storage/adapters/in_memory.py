"""In-memory object store adapter for tests and local scaffolding."""

from __future__ import annotations

from storage.models import StoredObject, StoredObjectWriteResult

__all__ = ["InMemoryObjectStore"]


class InMemoryObjectStore:
    """A process-local object store keyed by object path."""

    # TODO(production): Add delete(), exists(), list_keys() to match the extended
    # ObjectStore protocol. Add thread-safety (threading.Lock) for concurrent access
    # in multi-threaded test scenarios.

    def __init__(self) -> None:
        self._objects: dict[str, StoredObject] = {}

    def put_bytes(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredObjectWriteResult:
        object_metadata = metadata or {}
        stored = StoredObject(
            key=key,
            content=content,
            size_bytes=len(content),
            media_type=media_type,
            metadata=object_metadata,
        )
        self._objects[key] = stored
        return StoredObjectWriteResult(
            key=key,
            size_bytes=stored.size_bytes,
            media_type=stored.media_type,
            metadata=stored.metadata,
        )

    def get_bytes(self, key: str) -> StoredObject:
        stored = self._objects.get(key)
        if stored is None:
            raise KeyError(f"Stored object not found: {key}")
        return stored