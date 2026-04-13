"""Object storage protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from storage.models import StoredObject, StoredObjectWriteResult


@runtime_checkable
class ObjectStore(Protocol):
    """Store and retrieve raw document bytes."""

    def put_bytes(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredObjectWriteResult: ...

    def get_bytes(self, key: str) -> StoredObject: ...


__all__ = [
    "ObjectStore",
]