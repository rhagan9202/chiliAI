"""Object storage contracts and in-memory adapter."""

from __future__ import annotations

from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.adapters.s3_adapter import S3ObjectStore
from storage.models import StoredObject, StoredObjectWriteResult
from storage.protocols import ObjectStore

__all__ = [
    "InMemoryObjectStore",
    "LocalFsObjectStore",
    "ObjectStore",
    "S3ObjectStore",
    "StoredObject",
    "StoredObjectWriteResult",
]