"""Flow B alerts carry a human entity name (UXA-304).

Natively generated alerts used to store ``entity_label = entity_id`` and a
title of ``"High risk: provider-1"``, so the alert feed showed an internal
handle where the workbench showed the configured display field. Both now
resolve through ``config.display.entity_display_label``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from agent.coordinator import handle_graph_updated_for_analytics
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from analytics.explainability.service import create_explainability_service
from analytics.gnn.service import GnnService
from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    UiConfig,
    UiDisplayFieldsConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import (
    AlertsCreatedEvent,
    GraphUpdatedDocumentReference,
    GraphUpdatedEvent,
)
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.models import GraphUpsertResult
from graph.service import create_graph_service
from shared.types import (
    Alert,
    Entity,
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
)
from storage.adapters.in_memory import InMemoryObjectStore

STORAGE_KEY = "gk-display-label"


class _StubGnnService:
    """Duck-typed stand-in: the real service needs a persisted graph snapshot,
    which this test does not exercise."""

    def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse:
        return GnnAnalysisResponse(
            request_id="req-display-label",
            knowledge_base_id=request.knowledge_base_id,
            node_count=1,
            edge_count=0,
            communities=[],
        )


class _ContextSource:
    """Deterministic explanation context, as in the Flow B coordinator tests."""

    def load_context(
        self, *, knowledge_base_id: str, alert_id: str
    ) -> ExplanationContext:
        return ExplanationContext(
            knowledge_base_id=knowledge_base_id,
            alert=Alert(
                id=alert_id,
                entity_type="provider",
                entity_id="provider-1",
                severity="high",
                title="Outlier",
                reasoning="Outlier billing",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            explanation_items=[
                ExplanationItem(
                    source_id="provider-1",
                    source_type="risk_factor",
                    quote="anomaly",
                    rationale="Above peers.",
                    score=0.7,
                )
            ],
            subgraph=ExplanationSubgraph(node_ids=["provider-1"], edge_ids=[]),
            scores={"overall": 0.7},
            confidence=0.7,
        )


def _domain_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(
            name="medicare_fraud", display_name="Medicare Fraud", description=""
        ),
        entities=[
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                natural_key=["npi"],
                properties={
                    "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI")
                },
            )
        ],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        alerts=AlertsConfig(thresholds={}),
        ui=UiConfig(
            display_fields={"provider": UiDisplayFieldsConfig(title="npi")}
        ),
    )


def _event() -> GraphUpdatedEvent:
    return GraphUpdatedEvent(
        correlation_id="corr-display-label",
        documents=[
            GraphUpdatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-A",
                parsed_document_id="parsed-A",
                extraction_result_id="extract-A",
                validation_report_id="validate-A",
                upserted_entity_count=1,
                upserted_relationship_count=0,
                validation_storage_key="vk-display-label",
                graph_update_storage_key=STORAGE_KEY,
            )
        ],
    )


def _run(*, domain_config: DomainConfig | None) -> AlertsCreatedEvent:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        STORAGE_KEY,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        )
        .model_dump_json()
        .encode("utf-8"),
        media_type="application/json",
    )

    graph_repository = InMemoryGraphRepository()
    graph_repository.upsert_entities(
        "kb-1",
        [Entity(id="provider-1", type="provider", properties={"npi": "1234567890"})],
    )
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="provider-1",
                    signals=[
                        RiskSignal(signal_name="anomaly", value=0.7, weight=0.5),
                        RiskSignal(signal_name="velocity", value=0.7, weight=0.5),
                    ],
                )
            ]
        ),
        event_bus=event_bus,
    )

    handle_graph_updated_for_analytics(
        _event(),
        gnn_service=cast(GnnService, _StubGnnService()),
        risk_service=risk_service,
        explainability_service=create_explainability_service(
            _ContextSource(), event_bus=event_bus
        ),
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=object_store,
        domain_config=domain_config,
    )

    published = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(published) == 1
    return published[0]


def test_alert_carries_the_configured_display_field_as_its_entity_label() -> None:
    alerts = _run(domain_config=_domain_config()).alerts

    assert alerts[0].entity_label == "1234567890"


def test_alert_title_names_the_entity_rather_than_its_id() -> None:
    # The risk tier prefix is not what is under test here — the subject is.
    alerts = _run(domain_config=_domain_config()).alerts

    assert alerts[0].title.endswith(": 1234567890")
    assert "provider-1" not in alerts[0].title


def test_falls_back_to_the_entity_id_without_a_domain_config() -> None:
    # Unit scaffolding and older call sites pass no config; the alert must
    # still be produced rather than failing to resolve a name.
    alerts = _run(domain_config=None).alerts

    assert alerts[0].entity_label == "provider-1"
    assert alerts[0].title.endswith(": provider-1")
