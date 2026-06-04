"""Tests for config-driven graph entity detail projection (BL-012)."""

from __future__ import annotations

from pathlib import Path

import pytest

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.service import create_risk_service
from api._alert_store import InMemoryAlertProjectionRepository
from api._graph_entity_payload import build_graph_entity_detail
from config.loader import load_config
from config.schema import DomainConfig
from events.adapters.in_memory import InMemoryEventBus
from graph import InMemoryGraphRepository, create_graph_service
from knowledgebases import InMemoryKnowledgeBaseRepository
from shared.types import Entity, KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"


@pytest.mark.parametrize(
    "config_path",
    [
        DEFAULTS_DIR / "medicare_fraud.yaml",
        DEFAULTS_DIR / "food_supply_chain.yaml",
    ],
)
def test_graph_entity_detail_uses_domain_config_for_labels(
    config_path: Path,
) -> None:
    config: DomainConfig = load_config(config_path)
    primary_type = config.entities[0].name

    graph_repository = InMemoryGraphRepository()
    graph_repository.upsert_entities(
        "kb-1",
        [
            Entity(
                id="provider-204",
                type=primary_type,
                properties={"display_name": "Advanced Pain Specialists"},
            )
        ],
    )
    graph_service = create_graph_service(
        graph_repository,
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(), event_bus=InMemoryEventBus()
    )
    kb_repository = InMemoryKnowledgeBaseRepository()
    kb_repository.create(
        KnowledgeBase(
            id="kb-1",
            name="KB",
            description="d",
            status="ready",
            created_at=utc_now(),
        )
    )

    detail = build_graph_entity_detail(
        "provider-204",
        graph_service=graph_service,
        risk_service=risk_service,
        alert_repository=InMemoryAlertProjectionRepository(),
        kb_repository=kb_repository,
        domain_config=config,
    )

    assert detail is not None
    assert detail.entity.type == primary_type
    assert config.entities[0].display_label in detail.entity.summary
