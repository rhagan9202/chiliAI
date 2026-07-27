"""`GET /investigation/entities/{id}/locate` finds which KB holds an entity (UXA-104).

`/investigation/provider-1` without `?kb=` resolved against whatever knowledge
base the workspace happened to point at and died with "the selected entity
could not be loaded". Any bookmark, shared link, or refresh that dropped the
query landed there. The UI cannot offer "this entity is in <KB> — switch and
open it" without being able to ask where it actually lives.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_domain_config
from api.routers.investigation import (
    get_domain_config as router_get_domain_config,
    get_graph_service,
    get_knowledge_base_repository as router_get_knowledge_base_repository,
    router,
)
from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    ValidationConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.protocols import GraphServiceProtocol
from graph.service import create_graph_service
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import Entity, KnowledgeBase
from storage.adapters.in_memory import InMemoryObjectStore
from shared.utils import utc_now


def _domain_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        alerts=AlertsConfig(thresholds={}),
        validation=ValidationConfig(),
        auth=AuthConfig(enabled=False),
    )


@pytest.fixture()
def kb_repository() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(id="kb-1", name="First", description="", created_at=utc_now())
    )
    repository.create(
        KnowledgeBase(id="kb-2", name="Second", description="", created_at=utc_now())
    )
    return repository


@pytest.fixture()
def graph_service() -> GraphServiceProtocol:
    service = cast(
        GraphServiceProtocol,
        create_graph_service(
            InMemoryGraphRepository(),
            object_store=InMemoryObjectStore(),
            event_bus=InMemoryEventBus(),
        ),
    )
    # The entity lives in kb-2 only; kb-1 is the decoy the workspace might be
    # pointing at when a deep link arrives with no ?kb=.
    service.upsert_records_graph(
        "kb-2", [Entity(id="provider-1", type="provider", properties={})], []
    )
    return service


@pytest.fixture()
def client(
    graph_service: GraphServiceProtocol,
    kb_repository: InMemoryKnowledgeBaseRepository,
) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_domain_config] = _domain_config
    app.dependency_overrides[router_get_domain_config] = _domain_config
    app.dependency_overrides[router_get_knowledge_base_repository] = lambda: kb_repository
    with TestClient(app) as test_client:
        yield test_client


def test_reports_the_knowledge_base_that_holds_the_entity(client: TestClient) -> None:
    payload = client.get("/investigation/entities/provider-1/locate").json()

    assert [item["knowledge_base_id"] for item in payload["items"]] == ["kb-2"]


def test_names_the_knowledge_base_so_the_ui_can_offer_a_switch(client: TestClient) -> None:
    payload = client.get("/investigation/entities/provider-1/locate").json()

    assert payload["items"][0]["knowledge_base_name"] == "Second"


def test_reports_nothing_for_an_entity_that_exists_nowhere(client: TestClient) -> None:
    # "It is not here" and "it is somewhere else" are different answers, and
    # the UI must be able to tell them apart.
    payload = client.get("/investigation/entities/ghost-1/locate").json()

    assert payload["items"] == []
