"""Application state for analytics read services backing frontend API reads.

BL-012 de-seeded this object: alerts, cases, conversations, workflows, evidence
packs, and the investigation graph are now served from durable stores (see
``api/dependencies.py`` and the per-domain repositories). B2 (analytics.07)
moved the entity timeseries route off this object too — it is now served
directly from ``get_entity_series_source`` / ``get_timeseries_anomaly_store``
in ``api/dependencies.py`` — and then did the same for the risk detail route
(``get_risk_score_payload`` now assesses via the DI risk service). What
remains here is the RAG service handle used by the chat streaming path.
"""

from __future__ import annotations

from config.loader import load_config
from config.schema import DomainConfig
from events.adapters.in_memory import InMemoryEventBus
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryGraphContextExpander,
    InMemoryQueryEmbedder,
)
from rag.models import ContextRecord
from rag.protocols import RagServiceProtocol
from rag.service import create_rag_service

__all__ = ["ApiState", "create_api_state"]


class ApiState:
    """Own the RAG service handle backing chat conversations."""

    def __init__(
        self,
        domain_config: DomainConfig | None = None,
        *,
        rag_service: RagServiceProtocol | None = None,
    ) -> None:
        self._domain_config = domain_config or load_config()
        self._primary_entity_id = "provider-204"
        self._secondary_entity_id = "provider-118"
        self._event_bus = InMemoryEventBus()

        # When the gateway supplies a fully-wired RAG service we use it directly
        # (live embeddings/vectorstore/graph/LLM composition — see BL-001).
        # Falling back to the seeded in-memory pipeline keeps ApiState
        # self-contained for unit tests that construct it without DI.
        if rag_service is not None:
            self._rag_service = rag_service
        else:
            self._rag_service = create_rag_service(
                InMemoryQueryEmbedder(),
                InMemoryContextRetriever(records=self._build_context_records()),
                InMemoryAnswerGenerator(provider="in-memory", model_name="seeded-rag-model"),
                event_bus=self._event_bus,
                graph_context_expander=InMemoryGraphContextExpander(),
                domain_config=self._domain_config,
            )

    @property
    def rag_service(self) -> RagServiceProtocol:
        """The RAG service backing chat conversations and streaming responses."""
        return self._rag_service

    def _build_context_records(self) -> list[ContextRecord]:
        return [
            ContextRecord(
                record_id="record-1",
                content_id="content-1",
                embedding=[20.0, 16.0, 3.0, 4.0],
                content="Provider 204 shows repeated injection billing patterns with peer cohort deviation and graph-linked concentration.",
                metadata={"entity_id": self._primary_entity_id, "category": "alerts"},
            ),
            ContextRecord(
                record_id="record-2",
                content_id="content-2",
                embedding=[18.0, 15.0, 2.0, 4.0],
                content="North Harbor Imaging referral traffic is overly concentrated and linked to elevated utilization.",
                metadata={"entity_id": self._secondary_entity_id, "category": "network"},
            ),
        ]


def create_api_state(
    domain_config: DomainConfig | None = None,
    *,
    rag_service: RagServiceProtocol | None = None,
) -> ApiState:
    """Create the API application state.

    When ``rag_service`` is provided it replaces the seeded in-memory RAG
    pipeline — used by :func:`api.app.create_app` to inject a live
    embeddings → vectorstore → graph → LLM composition (see BL-001).
    """
    return ApiState(domain_config, rag_service=rag_service)
