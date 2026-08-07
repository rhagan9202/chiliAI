"""Binds built-in capabilities to the callables that run them.

`capabilities/executors.py` is the map; this is what puts anything in it. The
binding lives here rather than at import time because every real capability
needs services — a `Mapping -> Mapping` executor cannot reach a `RagService` on
its own, so the worker closes over its own instances and registers the closures
at startup.

Only capabilities with a real implementation are bound, and only when their
service is present. The rest stay absent deliberately: `execute()` reports
`capability_not_executable`, which is a truthful "registered but not runnable"
rather than a capability that looks available and fails at dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import cast

from analytics.peerstats.peer_analysis import PeerAnalysisService
from capabilities.executors import (
    CapabilityExecutor,
    ExecutionContext,
    register_executor,
)
from capabilities.models import CapabilityExecutionEnvelope
from capabilities.service import CapabilityRegistryService
from config.schema import CapabilitiesConfig
from connectors.service import ConnectorService
from connectors.status_adapter import (
    CONNECTOR_SYNC_STATUS_CAPABILITY_ID,
    execute_connector_sync_status_capability,
)
from rag.protocols import RagServiceProtocol

__all__ = ["PEER_CONTEXT_CAPABILITY_ID", "register_builtin_capability_executors"]

logger = logging.getLogger(__name__)

PEER_CONTEXT_CAPABILITY_ID = "analytics.peer_context"


def register_builtin_capability_executors(
    *,
    connector_service: ConnectorService | None,
    rag_service: RagServiceProtocol | None,
    peer_analysis_service: PeerAnalysisService | None,
    capability_registry: CapabilityRegistryService,
    capabilities_config: CapabilitiesConfig,
    domain_name: str | None,
    environment_tag: str | None,
) -> frozenset[str]:
    """Register every capability this process can actually execute.

    Returns the ids bound, so a caller can log or assert what is runnable
    rather than discovering it one failed workflow step at a time. A service
    that is absent leaves its capability unbound rather than bound-and-broken:
    `capability_not_executable` at authorization time is a clear answer,
    whereas a closure over a missing service fails only at dispatch.
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

    if rag_service is not None:
        # Imported here, not at module scope: `workflow_definitions/__init__`
        # reaches the coordinator, which imports this module, so a top-level
        # import is a cycle:
        #   builtin_executors -> workflow_definitions -> agent -> coordinator
        # Binding happens at worker startup, long after both are loaded.
        from workflow_definitions.rag_adapter import RAG_QUERY_CAPABILITY_ID

        register_executor(
            RAG_QUERY_CAPABILITY_ID,
            _rag_query_executor(
                rag_service=rag_service,
                capability_registry=capability_registry,
                domain_name=domain_name,
                environment_tag=environment_tag,
            ),
        )
        bound.add(RAG_QUERY_CAPABILITY_ID)

    if peer_analysis_service is not None:
        register_executor(
            PEER_CONTEXT_CAPABILITY_ID,
            _peer_context_executor(
                peer_analysis_service=peer_analysis_service,
                capabilities_config=capabilities_config,
            ),
        )
        bound.add(PEER_CONTEXT_CAPABILITY_ID)

    logger.info("Registered capability executors: %s", sorted(bound) or "none")
    return frozenset(bound)


def _connector_sync_status_executor(
    *,
    connector_service: ConnectorService,
    capability_registry: CapabilityRegistryService,
    domain_name: str | None,
    environment_tag: str | None,
) -> CapabilityExecutor:
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
        return _unwrap(
            execute_connector_sync_status_capability(
                connector_service=connector_service,
                capability_registry=capability_registry,
                # From the context, which `execute()` already authorized
                # against — no longer dug out of the business payload.
                actor_roles=list(context.actor_roles),
                knowledge_base_id=knowledge_base_id,
                connector_id=connector_id,
                domain_name=domain_name,
                environment_tag=environment_tag,
            )
        )

    return _run


def _rag_query_executor(
    *,
    rag_service: RagServiceProtocol,
    capability_registry: CapabilityRegistryService,
    domain_name: str | None,
    environment_tag: str | None,
) -> CapabilityExecutor:
    """Answer a question against the run's knowledge base."""

    from workflow_definitions.rag_adapter import execute_rag_query_capability

    def _run(
        payload: Mapping[str, object], context: ExecutionContext
    ) -> Mapping[str, object]:
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("rag.query requires a non-empty 'question' input.")
        knowledge_base_ids = _knowledge_base_ids(payload, context)
        if not knowledge_base_ids:
            raise ValueError("rag.query requires at least one knowledge base.")
        return _unwrap(
            execute_rag_query_capability(
                rag_service=rag_service,
                capability_registry=capability_registry,
                actor_roles=list(context.actor_roles),
                knowledge_base_ids=knowledge_base_ids,
                question=question,
                domain_name=domain_name,
                environment_tag=environment_tag,
            )
        )

    return _run


def _peer_context_executor(
    *,
    peer_analysis_service: PeerAnalysisService,
    capabilities_config: CapabilitiesConfig,
) -> CapabilityExecutor:
    """Return peer context for one entity metric.

    Flattens `PeerAnalysisResponse` — which carries a *list* of metric
    comparisons — to the manifest's single-metric shape, because the manifest is
    the published contract. `peer_count` maps to `cohort_size`: the same
    quantity under another name, so nothing the manifest promises is invented.
    """

    def _run(
        payload: Mapping[str, object], context: ExecutionContext
    ) -> Mapping[str, object]:
        if not capabilities_config.peer_stats:
            raise ValueError(
                "analytics.peer_context requires the 'peer_stats' domain capability."
            )
        knowledge_base_id = payload.get("knowledge_base_id") or context.knowledge_base_id
        entity_id = payload.get("entity_id")
        metric_name = payload.get("metric_name")
        if not isinstance(knowledge_base_id, str) or not isinstance(entity_id, str):
            raise ValueError(
                "analytics.peer_context requires string 'knowledge_base_id' and "
                "'entity_id' inputs."
            )
        if not isinstance(metric_name, str) or not metric_name:
            raise ValueError("analytics.peer_context requires a 'metric_name' input.")

        response = peer_analysis_service.compare_entity(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metric_name=metric_name,
        )
        comparison = next(
            (metric for metric in response.metrics if metric.metric_name == metric_name),
            None,
        )
        if comparison is None:
            # Absent is not zero. Returning z_score=0.0 would read as
            # "perfectly average" for an entity that has no comparison at all.
            raise ValueError(
                f"No peer comparison for entity '{entity_id}' metric '{metric_name}'."
            )
        return {
            "entity_id": response.entity_id,
            "metric_name": comparison.metric_name,
            "peer_count": comparison.cohort_size,
            "z_score": comparison.z_score,
        }

    return _run


def _knowledge_base_ids(
    payload: Mapping[str, object], context: ExecutionContext
) -> list[str]:
    """Knowledge bases to query, from the payload or the run's own scope."""

    raw = payload.get("knowledge_base_ids")
    if isinstance(raw, list):
        # `json.loads`-shaped input narrows to list[Unknown]; pin as object
        # before iterating, the same pattern the jsonb decoders use.
        return [str(item) for item in cast(list[object], raw)]
    single = payload.get("knowledge_base_id") or context.knowledge_base_id
    return [single] if isinstance(single, str) else []


def _unwrap(envelope: CapabilityExecutionEnvelope) -> Mapping[str, object]:
    """Turn an adapter envelope into an executor result.

    A failed envelope raises so `execute()` reports it as a failed capability
    call carrying the adapter's own reason, rather than returning a success
    whose output is an error.
    """

    if not envelope.success:
        raise RuntimeError(envelope.error_message or "capability call failed")
    # `output` is optional; an authorized call that produced nothing is an
    # empty result, not a missing one.
    return envelope.output or {}
