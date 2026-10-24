"""Deployment-shape checks that need only a resolved ``DomainConfig``.

Each process that serves a pack (the API and the worker) applies these at boot,
and the API applies them to every hot-swap candidate, with its own effective
event-bus backend: only the caller knows whether the environment overrides the
pack's ``events`` section.
"""

from __future__ import annotations

from config.schema import DatabaseConfig, DomainConfig, GraphDbConfig, VectorStoreConfig
from shared.exceptions import ConfigurationError

__all__ = ["process_local_state_stores", "require_shared_state_stores"]


def process_local_state_stores(config: DomainConfig) -> list[str]:
    """Name the stateful sections whose backend lives in one process's memory.

    An omitted section falls back to its schema default, which is ``in_memory``
    for all three — so a base pack with no infra block reports all of them.
    """

    stores: list[str] = []
    if (config.database or DatabaseConfig()).backend == "in_memory":
        stores.append("database")
    if (config.graph or GraphDbConfig()).backend == "in_memory":
        stores.append("graph")
    if (config.vectorstore or VectorStoreConfig()).backend == "in_memory":
        stores.append("vectorstore")
    return stores


def require_shared_state_stores(config: DomainConfig, *, event_bus_backend: str) -> None:
    """Reject in-memory state stores when the API and worker are separate processes.

    A Redis event bus means the API publishes and a separate worker consumes.
    An in-memory database/graph/vector store is then private to each process:
    the API accepts records the worker can never read and the worker builds a
    graph the API can never serve, with no error anywhere. An in-process bus
    (tests, single-process runs) shares one memory, so it is left alone.
    """

    if event_bus_backend != "redis":
        return
    local = process_local_state_stores(config)
    if not local:
        return
    raise ConfigurationError(
        f"Pack '{config.domain.name}' keeps {', '.join(local)} in process memory, "
        "but the event bus is redis, so the API and worker run as separate "
        "processes and cannot share that state. Pin shared backends for these "
        "sections, or layer an environment overlay that does via "
        "CHILI_CONFIG_OVERLAY_PATH (e.g. config/overlays/medicare_fraud_dev.yaml; "
        "`make dev-domain` applies config/overlays/<pack>_dev.yaml automatically)."
    )
