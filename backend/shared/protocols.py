"""Cross-cutting protocols consumed by multiple backend modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from config.schema import DomainConfig


class StoredObjectWriteResult(BaseModel):
    """Metadata returned after storing an object."""

    key: str
    size_bytes: int = Field(ge=0)
    media_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class StoredObject(BaseModel):
    """Stored object data plus metadata."""

    key: str
    content: bytes
    size_bytes: int = Field(ge=0)
    media_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class Configurable(Protocol):
    """A module or service that accepts domain configuration at init time."""

    def configure(self, config: DomainConfig) -> None: ...


@runtime_checkable
class ObjectStoreProtocol(Protocol):
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


# TODO(production): Add cross-cutting protocols consumed by multiple modules:
# - HealthCheckable: async def health_check() -> HealthStatus for readiness probes
# - Lifecycle: async def start() / async def stop() for graceful startup/shutdown
# - Measurable: def get_metrics() -> dict[str, float] for observability export
# See docs/architecture.md §12 for monitoring and observability requirements.


__all__ = [
    "Configurable",
    "ObjectStoreProtocol",
    "StoredObject",
    "StoredObjectWriteResult",
]
