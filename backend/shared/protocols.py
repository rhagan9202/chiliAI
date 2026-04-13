"""Cross-cutting protocols consumed by multiple backend modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from config.schema import DomainConfig


@runtime_checkable
class Configurable(Protocol):
    """A module or service that accepts domain configuration at init time."""

    def configure(self, config: DomainConfig) -> None: ...


# TODO(production): Add cross-cutting protocols consumed by multiple modules:
# - HealthCheckable: async def health_check() -> HealthStatus for readiness probes
# - Lifecycle: async def start() / async def stop() for graceful startup/shutdown
# - Measurable: def get_metrics() -> dict[str, float] for observability export
# See docs/architecture.md §12 for monitoring and observability requirements.


__all__ = [
    "Configurable",
]
