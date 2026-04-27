"""Tests for the investigation router (entity detail, neighborhood, search)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.investigation import get_graph_service, router
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.protocols import GraphServiceProtocol
from graph.service import create_graph_service
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def _build_graph_service() -> GraphServiceProtocol:
    return cast(
        GraphServiceProtocol,
        create_graph_service(
            InMemoryGraphRepository(),
            object_store=InMemoryObjectStore(),
            event_bus=InMemoryEventBus(),
        ),
    )


def _seed_entities(graph_service: GraphServiceProtocol, knowledge_base_id: str) -> None:
    repository = cast(
        InMemoryGraphRepository,
        getattr(graph_service, "_repository"),
    )
    repository.upsert_entities(
        knowledge_base_id,
        [
            Entity(
                id="entity-1",
                type="provider",
                properties={"name": "Acme Health Systems"},
            ),
            Entity(
                id="entity-2",
                type="claim",
                properties={"description": "Acme service claim"},
            ),
            Entity(
                id="entity-3",
                type="claim",
                properties={"description": "Beta service claim"},
            ),
        ],
    )
    repository.upsert_relationships(
        knowledge_base_id,
        [
            Relationship(
                id="rel-1",
                type="submitted_by",
                source_id="entity-2",
                target_id="entity-1",
            ),
            Relationship(
                id="rel-2",
                type="submitted_by",
                source_id="entity-3",
                target_id="entity-1",
            ),
        ],
    )


@pytest.fixture()
def graph_service() -> GraphServiceProtocol:
    service = _build_graph_service()
    _seed_entities(service, "kb-1")
    return service


@pytest.fixture()
def client(graph_service: GraphServiceProtocol) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    with TestClient(app) as test_client:
        yield test_client


def test_get_entity_returns_entity_when_found(client: TestClient) -> None:
    response = client.get("/investigation/entities/entity-1", params={"kb_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"]["id"] == "entity-1"
    assert payload["entity"]["type"] == "provider"
    assert payload["entity"]["properties"]["name"] == "Acme Health Systems"


def test_get_entity_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/investigation/entities/missing", params={"kb_id": "kb-1"})

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_get_entity_requires_kb_id(client: TestClient) -> None:
    response = client.get("/investigation/entities/entity-1")
    assert response.status_code == 422


def test_get_neighborhood_returns_subgraph(client: TestClient) -> None:
    response = client.get(
        "/investigation/entities/entity-1/neighborhood",
        params={"kb_id": "kb-1", "depth": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["center_entity_id"] == "entity-1"
    returned_entity_ids = {entity["id"] for entity in payload["entities"]}
    assert {"entity-1", "entity-2", "entity-3"} == returned_entity_ids
    returned_relationship_ids = {rel["id"] for rel in payload["relationships"]}
    assert {"rel-1", "rel-2"} == returned_relationship_ids


def test_get_neighborhood_uses_default_depth_two(client: TestClient) -> None:
    response = client.get(
        "/investigation/entities/entity-1/neighborhood",
        params={"kb_id": "kb-1"},
    )

    assert response.status_code == 200
    assert response.json()["center_entity_id"] == "entity-1"


def test_get_neighborhood_returns_404_when_entity_missing(client: TestClient) -> None:
    response = client.get(
        "/investigation/entities/ghost/neighborhood",
        params={"kb_id": "kb-1"},
    )

    assert response.status_code == 404


def test_get_neighborhood_rejects_depth_above_max(client: TestClient) -> None:
    response = client.get(
        "/investigation/entities/entity-1/neighborhood",
        params={"kb_id": "kb-1", "depth": 6},
    )

    assert response.status_code == 422


def test_get_neighborhood_rejects_depth_below_minimum(client: TestClient) -> None:
    response = client.get(
        "/investigation/entities/entity-1/neighborhood",
        params={"kb_id": "kb-1", "depth": 0},
    )

    assert response.status_code == 422


def test_search_returns_matching_entities(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": "acme"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    returned_ids = {item["id"] for item in payload["items"]}
    assert returned_ids == {"entity-1", "entity-2"}


def test_search_returns_empty_for_no_match(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": "no-such-term"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0


def test_search_requires_q_parameter(client: TestClient) -> None:
    response = client.get("/investigation/search", params={"kb_id": "kb-1"})
    assert response.status_code == 422


def test_search_requires_q_to_be_non_empty(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": ""},
    )
    assert response.status_code == 422


def test_search_rejects_limit_above_max(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": "acme", "limit": 501},
    )
    assert response.status_code == 422


def test_search_rejects_negative_offset(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": "acme", "offset": -1},
    )
    assert response.status_code == 422


def test_search_respects_limit_and_offset(client: TestClient) -> None:
    response = client.get(
        "/investigation/search",
        params={"kb_id": "kb-1", "q": "acme", "limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "entity-2"


def test_get_graph_service_default_factory_returns_protocol_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = _build_graph_service()

    import api.dependencies as dependencies

    monkeypatch.setattr(
        dependencies,
        "get_graph_service",
        lambda: sentinel,
    )

    assert get_graph_service() is sentinel
