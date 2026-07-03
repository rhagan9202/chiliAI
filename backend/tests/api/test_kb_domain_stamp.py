"""Tests for KnowledgeBase domain stamping (E7).

New KBs are stamped with the active ``DomainConfig.domain.name`` at creation;
legacy KBs (created before stamping, ``domain is None``) remain fully valid in
list/detail/status flows — a missing stamp is "unknown", never an error.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_event_bus,
    get_graph_service,
    get_knowledge_base_repository,
    get_object_store,
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
from graph.models import GraphMetrics
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from shared.types import KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _build_config(domain_name: str = "medicare_fraud") -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(
            name=domain_name,
            display_name=domain_name.replace("_", " ").title(),
            description="Test domain",
        ),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=False),
        validation=ValidationConfig(
            max_file_size_mb=1,
            allowed_content_types=["text/plain", "application/json"],
        ),
        alerts=AlertsConfig(thresholds={}),
    )


class _MetricsOnlyGraphService:
    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics:
        del knowledge_base_id
        return GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)


def _make_client(
    repository: InMemoryKnowledgeBaseRepository,
    domain_name: str,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_event_bus] = InMemoryEventBus
    app.dependency_overrides[get_domain_config] = lambda: _build_config(domain_name)
    app.dependency_overrides[get_object_store] = InMemoryObjectStore
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = _MetricsOnlyGraphService
    return TestClient(app)


@pytest.fixture()
def repository() -> InMemoryKnowledgeBaseRepository:
    return InMemoryKnowledgeBaseRepository()


@pytest.fixture()
def client(repository: InMemoryKnowledgeBaseRepository) -> Iterator[TestClient]:
    with _make_client(repository, "medicare_fraud") as test_client:
        yield test_client


class TestStampOnCreate:
    def test_create_stamps_active_domain_name(
        self,
        client: TestClient,
        repository: InMemoryKnowledgeBaseRepository,
    ) -> None:
        response = client.post(
            "/knowledgebases",
            json={"name": "Stamped KB", "description": "created under medicare"},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["domain"] == "medicare_fraud"

        persisted = repository.get(payload["id"])
        assert persisted is not None
        assert persisted.domain == "medicare_fraud"

    def test_stamp_follows_the_active_config_not_a_constant(
        self,
        repository: InMemoryKnowledgeBaseRepository,
    ) -> None:
        with _make_client(repository, "food_supply_chain") as client:
            response = client.post(
                "/knowledgebases",
                json={"name": "Food KB", "description": ""},
            )

        assert response.status_code == 201
        assert response.json()["domain"] == "food_supply_chain"


class TestDomainFieldInResponses:
    def test_list_and_detail_expose_domain(
        self,
        client: TestClient,
    ) -> None:
        created = client.post(
            "/knowledgebases",
            json={"name": "Visible KB", "description": ""},
        ).json()

        listing = client.get("/knowledgebases")
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert [item["domain"] for item in items] == ["medicare_fraud"]

        detail = client.get(f"/knowledgebases/{created['id']}")
        assert detail.status_code == 200
        assert detail.json()["domain"] == "medicare_fraud"

    def test_stamp_survives_status_projection(
        self,
        client: TestClient,
        repository: InMemoryKnowledgeBaseRepository,
    ) -> None:
        created = client.post(
            "/knowledgebases",
            json={"name": "Projected KB", "description": ""},
        ).json()
        # A registered document flips the projection from active -> building;
        # the domain stamp must survive the update_summary round trip.
        repository.add_document(
            DocumentRecord(
                id="doc-1",
                knowledge_base_id=created["id"],
                filename="claims.json",
            )
        )

        detail = client.get(f"/knowledgebases/{created['id']}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "building"
        assert payload["domain"] == "medicare_fraud"


class TestLegacyKnowledgeBaseTolerance:
    """KBs created before stamping (domain=None) stay valid everywhere."""

    @pytest.fixture()
    def legacy_kb_id(self, repository: InMemoryKnowledgeBaseRepository) -> str:
        legacy = KnowledgeBase(
            id="kb-legacy",
            name="Legacy KB",
            description="Created before domain stamping",
            created_at=utc_now(),
        )
        assert legacy.domain is None
        repository.create(legacy)
        return legacy.id

    def test_legacy_kb_listed_with_null_domain(
        self,
        client: TestClient,
        legacy_kb_id: str,
    ) -> None:
        response = client.get("/knowledgebases")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        item = payload["items"][0]
        assert item["id"] == legacy_kb_id
        assert item["domain"] is None

    def test_legacy_kb_detail_with_null_domain(
        self,
        client: TestClient,
        legacy_kb_id: str,
    ) -> None:
        response = client.get(f"/knowledgebases/{legacy_kb_id}")

        assert response.status_code == 200
        assert response.json()["domain"] is None

    def test_legacy_kb_document_status_flow_succeeds(
        self,
        client: TestClient,
        repository: InMemoryKnowledgeBaseRepository,
        legacy_kb_id: str,
    ) -> None:
        repository.add_document(
            DocumentRecord(
                id="doc-legacy",
                knowledge_base_id=legacy_kb_id,
                filename="old.json",
            )
        )

        response = client.get(f"/knowledgebases/{legacy_kb_id}/documents")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == "doc-legacy"

    def test_legacy_snapshot_without_domain_key_deserializes(self) -> None:
        """Persisted pre-stamp snapshots load with domain=None, not an error."""
        object_store = InMemoryObjectStore()
        first = ObjectStoreKnowledgeBaseRepository(object_store)
        first.create(
            KnowledgeBase(
                id="kb-old",
                name="Old KB",
                description="",
                created_at=utc_now(),
            )
        )

        reloaded = ObjectStoreKnowledgeBaseRepository(object_store).get("kb-old")

        assert reloaded is not None
        assert reloaded.domain is None
