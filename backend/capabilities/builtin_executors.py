"""Binds built-in capabilities to the callables that run them.

`capabilities/executors.py` is the map; this is what puts anything in it. The
binding lives here rather than at import time because every real capability
needs services — a `Mapping -> Mapping` executor cannot reach a
`ConnectorService` on its own, so the worker closes over its own instances and
registers the closures at startup.

Only capabilities with a real implementation are bound. The rest stay absent
deliberately: `execute()` reports `capability_not_executable`, which is a
truthful "registered but not implemented" rather than a pretend success.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from capabilities.executors import ExecutionContext, register_executor
from capabilities.service import CapabilityRegistryService
from connectors.service import ConnectorService
from connectors.status_adapter import (
    CONNECTOR_SYNC_STATUS_CAPABILITY_ID,
    execute_connector_sync_status_capability,
)

__all__ = ["register_builtin_capability_executors"]

logger = logging.getLogger(__name__)


def register_builtin_capability_executors(
    *,
    connector_service: ConnectorService | None,
    capability_registry: CapabilityRegistryService,
    domain_name: str | None,
    environment_tag: str | None,
) -> frozenset[str]:
    """Register every capability this process can actually execute.

    Returns the ids bound, so a caller can log or assert what is runnable
    rather than discovering it one failed workflow step at a time.
    """

    bound: set[str] = set()

    if connector_service is not None:
        register_executor(
            CONNECTOR_SYNC_STATUS_CAPABILITY_ID,
            _connector_sync_status_executor(
                connector_service=connector_service,
                capability_registry=capability_registry,
                domain_name=domain_name,
                environment_tag=environment_tag,
            ),
        )
        bound.add(CONNECTOR_SYNC_STATUS_CAPABILITY_ID)

    logger.info("Registered capability executors: %s", sorted(bound) or "none")
    return frozenset(bound)


def _connector_sync_status_executor(
    *,
    connector_service: ConnectorService,
    capability_registry: CapabilityRegistryService,
    domain_name: str | None,
    environment_tag: str | None,
):  # type: ignore[no-untyped-def]
    """Adapt the existing envelope-returning adapter to the executor shape.

    The adapter predates `execute()` and authorizes internally, so
    authorization runs twice on this path. That is a redundant read, not a
    weaker check — and reusing the tested adapter is worth more than saving it.
    """

    def _run(
        payload: Mapping[str, object], context: ExecutionContext
    ) -> Mapping[str, object]:
        knowledge_base_id = payload.get("knowledge_base_id") or context.knowledge_base_id
        connector_id = payload.get("connector_id")
        if not isinstance(knowledge_base_id, str) or not isinstance(connector_id, str):
            raise ValueError(
                "connector.sync.status requires string 'knowledge_base_id' and "
                "'connector_id' inputs."
            )
        envelope = execute_connector_sync_status_capability(
            connector_service=connector_service,
            capability_registry=capability_registry,
            # From the context, which `execute()` already authorized against —
            # no longer dug out of the business payload and re-narrowed.
            actor_roles=list(context.actor_roles),
            knowledge_base_id=knowledge_base_id,
            connector_id=connector_id,
            domain_name=domain_name,
            environment_tag=environment_tag,
        )
        if not envelope.success:
            # Raised so `execute()` reports it as a failed capability call with
            # the adapter's own reason, rather than returning a success
            # envelope whose output is an error.
            raise RuntimeError(envelope.error_message or "capability call failed")
        # `output` is optional on the envelope; an authorized call that
        # produced nothing is an empty result, not a missing one.
        return envelope.output or {}

    return _run
