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

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def list_keys(self, prefix: str) -> list[str]: ...

    # TODO(production): Extend ObjectStore protocol with operations required for
    # large object and production lifecycle management:
    # - paginated list_keys(prefix: str, limit: int, cursor: str | None) -> ListResult
    # - get_stream(key: str) -> Iterator[bytes] for large object streaming
    # - put_stream(key: str, chunks: Iterator[bytes], ...) -> StoredObjectWriteResult
    # - generate_presigned_url(key: str, expires_in: int) -> str (S3/GCS download links)
    # Add production adapters: S3ObjectStore, GCSObjectStore, MinioObjectStore.


__all__ = [
    "ObjectStore",
]