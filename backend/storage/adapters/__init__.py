"""Object store adapters."""

from __future__ import annotations

from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.adapters.s3_adapter import S3ObjectStore

__all__ = ["InMemoryObjectStore", "LocalFsObjectStore", "S3ObjectStore"]