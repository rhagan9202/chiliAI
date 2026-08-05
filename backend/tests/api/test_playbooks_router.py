"""Tests for KB-scoped playbook API routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import create_app
from api.contracts import PlaybookImportRequestPayload, PlaybookPublishRequestPayload
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_playbook_repository,
    get_playbook_service,
)
from api.middleware.auth import User, get_current_user
from api.routers import playbooks as playbooks_router
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig, FraudPlaybookConfig
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookImportArtifact, PlaybookSnapshot
from playbooks.service import PlaybookService
from shared.types import KnowledgeBase


BASE_TIME = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
SEED_PLAYBOOK_ID = "provider_billing_spike_review"


def _domain_config(*, auth_enabled: bool = False) -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=auth_enabled)})


def _repository_with_kbs() -> InMemoryKnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id="kb-1",
            name="Playbook KB",
            description="Playbook API test KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    repository.create(
        KnowledgeBase(
            id="kb-2",
            name="Other KB",
            description="Unauthorized KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    return repository


def _repository_service(
    config: DomainConfig | None = None,
) -> tuple[InMemoryPlaybookRepository, PlaybookService]:
    repository = InMemoryPlaybookRepository()
    return repository, PlaybookService(
        repository=repository,
        domain_config=config or _domain_config(),
    )


def _viewer(*, knowledge_base_ids: list[str] | None = None) -> User:
    return User(
        user_id="viewer-1",
        roles=["viewer"],
        knowledge_base_ids=knowledge_base_ids,
    )


def _admin() -> User:
    return User(user_id="admin-user", roles=["admin"], knowledge_base_ids=["kb-1"])


def test_list_playbooks_returns_seed_and_published_versions() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)

    seeds = playbooks_router.list_playbooks(
        "kb-1",
        50,
        0,
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )
    published = playbooks_router.publish_playbook(
        "kb-1",
        SEED_PLAYBOOK_ID,
        PlaybookPublishRequestPayload(version="v1"),
        kb_repository,
        repository,
        service,
        config,
        _admin(),
    )
    listed = playbooks_router.list_playbooks(
        "kb-1",
        50,
        0,
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )

    assert seeds.total >= 3
    assert {item.id for item in seeds.items} >= {
        SEED_PLAYBOOK_ID,
        "peer_outlier_provider_review",
        "identity_mismatch_review",
    }
    assert published.definition.id == SEED_PLAYBOOK_ID
    assert published.published_by == "admin-user"
    assert [(item.playbook_id, item.version) for item in listed.published] == [
        (SEED_PLAYBOOK_ID, "v1")
    ]


def test_list_playbooks_reports_published_pagination_metadata() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)
    admin = _admin()

    for playbook_id in (SEED_PLAYBOOK_ID, "peer_outlier_provider_review"):
        playbooks_router.publish_playbook(
            "kb-1",
            playbook_id,
            PlaybookPublishRequestPayload(version="v1"),
            kb_repository,
            repository,
            service,
            config,
            admin,
        )

    listed = playbooks_router.list_playbooks(
        "kb-1",
        1,
        0,
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )

    assert len(listed.published) == 1
    assert listed.published_total == 2
    assert listed.published_limit == 1
    assert listed.published_offset == 0


def test_published_playbooks_are_scoped_to_knowledge_base() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)

    playbooks_router.publish_playbook(
        "kb-1",
        SEED_PLAYBOOK_ID,
        PlaybookPublishRequestPayload(version="v1"),
        kb_repository,
        repository,
        service,
        config,
        _admin(),
    )

    kb_1 = playbooks_router.list_playbooks(
        "kb-1",
        50,
        0,
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )
    kb_2 = playbooks_router.list_playbooks(
        "kb-2",
        50,
        0,
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )

    assert [(item.playbook_id, item.version) for item in kb_1.published] == [
        (SEED_PLAYBOOK_ID, "v1")
    ]
    assert kb_2.published == []
    assert kb_2.published_total == 0


def test_list_playbooks_adopts_legacy_snapshots_for_authorized_kb() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)
    repository.upsert_snapshot(
        PlaybookSnapshot(
            snapshot_id="__legacy__:medicare_fraud:external_review:v3",
            knowledge_base_id="__legacy__",
            domain_name="medicare_fraud",
            playbook_id="external_review",
            version="v3",
            status="published",
            definition=FraudPlaybookConfig(
                id="external_review",
                version="v3",
                title="External Review",
                status="published",
            ),
            source="api_import",
            published_by="admin-legacy",
        )
    )

    listed = playbooks_router.list_playbooks(
        "kb-1",
        50,
        0,
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )

    assert [(item.knowledge_base_id, item.playbook_id, item.version) for item in listed.published] == [
        ("kb-1", "external_review", "v3")
    ]
    assert (
        repository.get_snapshot(
            knowledge_base_id="kb-1",
            domain_name="medicare_fraud",
            playbook_id="external_review",
            version="v3",
        )
        is not None
    )


def test_get_playbook_version_finds_config_seed_beyond_first_page() -> None:
    config = _domain_config()
    seed = config.playbooks.items[0]
    playbooks = [
        seed.model_copy(update={"id": f"synthetic_playbook_{index}"}, deep=True)
        for index in range(101)
    ]
    config = config.model_copy(
        update={
            "playbooks": config.playbooks.model_copy(
                update={"items": playbooks},
                deep=True,
            )
        },
        deep=True,
    )
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)

    response = playbooks_router.get_playbook_version(
        "kb-1",
        "synthetic_playbook_100",
        "v1",
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )

    assert response.id == "synthetic_playbook_100"


def test_publish_playbook_requires_admin_and_uses_authenticated_actor() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)

    published = playbooks_router.publish_playbook(
        "kb-1",
        SEED_PLAYBOOK_ID,
        PlaybookPublishRequestPayload(version="v1"),
        kb_repository,
        repository,
        service,
        config,
        User(user_id="admin-from-token", roles=["admin"], knowledge_base_ids=["kb-1"]),
    )

    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: _domain_config(auth_enabled=True)
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="viewer-from-token", roles=["viewer"], knowledge_base_ids=["kb-1"]
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_playbook_repository] = lambda: repository
    app.dependency_overrides[get_playbook_service] = lambda: service

    with TestClient(app) as client:
        publish_response = client.post(
            f"/knowledgebases/kb-1/playbooks/{SEED_PLAYBOOK_ID}/publish",
            json={"version": "v1"},
        )
        import_response = client.post(
            "/knowledgebases/kb-1/playbooks/import",
            json={
                "artifact": {
                    "schema_version": "playbooks.v1",
                    "domain_name": "medicare_fraud",
                    "catalog_version": "external-v1",
                    "playbooks": [],
                }
            },
        )

    assert published.published_by == "admin-from-token"
    assert publish_response.status_code == 403
    assert import_response.status_code == 403


def test_playbook_routes_hide_unauthorized_kb() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)
    scoped_user = _viewer(knowledge_base_ids=["kb-1"])

    with pytest.raises(HTTPException) as list_exc:
        playbooks_router.list_playbooks(
            "kb-2",
            50,
            0,
            kb_repository,
            repository,
            service,
            config,
            scoped_user,
        )
    with pytest.raises(HTTPException) as detail_exc:
        playbooks_router.get_playbook_version(
            "kb-2",
            SEED_PLAYBOOK_ID,
            "v1",
            kb_repository,
            repository,
            service,
            config,
            scoped_user,
        )

    assert list_exc.value.status_code == 404
    assert detail_exc.value.status_code == 404


def test_export_import_round_trips_domain_artifact() -> None:
    config = _domain_config()
    kb_repository = _repository_with_kbs()
    repository, service = _repository_service(config)
    admin = _admin()

    playbooks_router.publish_playbook(
        "kb-1",
        SEED_PLAYBOOK_ID,
        PlaybookPublishRequestPayload(version="v1"),
        kb_repository,
        repository,
        service,
        config,
        admin,
    )
    exported = playbooks_router.export_playbooks(
        "kb-1",
        kb_repository,
        repository,
        service,
        config,
        _viewer(),
    )
    imported = playbooks_router.import_playbooks(
        "kb-1",
        PlaybookImportRequestPayload(artifact=exported.artifact),
        kb_repository,
        repository,
        service,
        config,
        admin,
    )

    artifact = PlaybookImportArtifact.model_validate(exported.artifact)
    assert artifact.domain_name == "medicare_fraud"
    assert [playbook.id for playbook in artifact.playbooks] == [SEED_PLAYBOOK_ID]
    assert imported.domain_name == "medicare_fraud"
    assert imported.imported_count == 1
