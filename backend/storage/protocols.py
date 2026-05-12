"""Object storage protocol."""

from __future__ import annotations

from shared.protocols import ObjectStoreProtocol

ObjectStore = ObjectStoreProtocol

# TODO(production): Extend ObjectStoreProtocol with operations required for
# large object and production lifecycle management:
# - paginated list_keys(prefix: str, limit: int, cursor: str | None) -> ListResult
# - get_stream(key: str) -> Iterator[bytes] for large object streaming
# - put_stream(key: str, chunks: Iterator[bytes], ...) -> StoredObjectWriteResult
# - generate_presigned_url(key: str, expires_in: int) -> str (S3/GCS download links)
# Add production adapters: S3ObjectStore, GCSObjectStore, MinioObjectStore.


__all__ = [
    "ObjectStore",
]