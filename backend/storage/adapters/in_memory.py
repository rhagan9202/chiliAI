"""In-memory object store adapter for tests and local scaffolding."""

from __future__ import annotations

from storage.models import StoredObject, StoredObjectWriteResult

__all__ = ["InMemoryObjectStore"]


class InMemoryObjectStore:
    """A process-local object store keyed by object path."""

    # TODO(production): Add thread-safety (threading.Lock) for concurrent access
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

    def delete(self, key: str) -> None:
        """Remove an object by key; missing keys are treated as a no-op."""
        self._objects.pop(key, None)

    def exists(self, key: str) -> bool:
        """Return whether an object exists for the provided key."""
        return key in self._objects

    def list_keys(self, prefix: str) -> list[str]:
        """Return all stored keys that start with the provided prefix."""
        return sorted(key for key in self._objects if key.startswith(prefix))
