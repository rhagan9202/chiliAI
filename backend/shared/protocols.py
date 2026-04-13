"""Cross-cutting protocols consumed by multiple backend modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from config.schema import DomainConfig


@runtime_checkable
class Configurable(Protocol):
    """A module or service that accepts domain configuration at init time."""

    def configure(self, config: DomainConfig) -> None: ...


__all__ = [
    "Configurable",
]
