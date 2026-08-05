from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.loader import load_config
from config.schema import FraudPlaybookConfig
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import (
    PlaybookImportArtifact,
    PlaybookPublishRequest,
    PlaybookSnapshot,
)
from playbooks.service import PlaybookService

_KB_ID = "kb-playbooks"


def _service() -> PlaybookService:
    return PlaybookService(
        repository=InMemoryPlaybookRepository(),
        domain_config=load_config(),
    )


def _repository_service() -> tuple[InMemoryPlaybookRepository, PlaybookService]:
    repository = InMemoryPlaybookRepository()
    return repository, PlaybookService(
        repository=repository,
        domain_config=load_config(),
    )


def test_list_config_playbooks_returns_config_authored_definitions() -> None:
    service = _service()

    page = service.list_config_playbooks(domain_name="medicare_fraud", limit=50, offset=0)

    assert page.total >= 3
    assert {item.id for item in page.items} >= {
        "provider_billing_spike_review",
        "peer_outlier_provider_review",
        "identity_mismatch_review",
    }


def test_publish_config_playbook_creates_immutable_snapshot() -> None:
    service = _service()

    first = service.publish_config_playbook(
        PlaybookPublishRequest(
            knowledge_base_id=_KB_ID,
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            actor_user_id="admin-1",
        )
    )
    second = service.publish_config_playbook(
        PlaybookPublishRequest(
            knowledge_base_id=_KB_ID,
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            actor_user_id="admin-1",
        )
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.status == "published"
    assert first.definition.id == "provider_billing_spike_review"


def test_import_export_round_trips_playbooks() -> None:
    service = _service()
    service.publish_config_playbook(
        PlaybookPublishRequest(
            knowledge_base_id=_KB_ID,
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            actor_user_id="admin-1",
        )
    )

    artifact = service.export_domain_playbooks(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
    )
    imported = service.import_playbooks(
        PlaybookImportArtifact.model_validate_json(artifact.model_dump_json()),
        knowledge_base_id=_KB_ID,
        actor_user_id="admin-2",
    )

    assert imported.domain_name == "medicare_fraud"
    assert imported.imported_count >= 1


def test_import_accepts_non_seed_playbook_definitions() -> None:
    service = _service()

    result = service.import_playbooks(
        PlaybookImportArtifact(
            domain_name="medicare_fraud",
            catalog_version="external-v1",
            playbooks=[
                FraudPlaybookConfig(
                    id="external_review",
                    version="v3",
                    title="External Review",
                    summary="Imported from another catalog.",
                    status="draft",
                )
            ],
        ),
        knowledge_base_id=_KB_ID,
        actor_user_id="admin-2",
    )

    artifact = service.export_domain_playbooks(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
    )

    assert result.snapshot_ids == ["kb-playbooks:medicare_fraud:external_review:v3"]
    assert {playbook.id for playbook in artifact.playbooks} == {"external_review"}
    assert artifact.playbooks[0].status == "published"


def test_export_adopts_legacy_snapshots_for_target_knowledge_base() -> None:
    repository, service = _repository_service()
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
                summary="Migrated from the domain-only snapshot table.",
                status="published",
            ),
            source="api_import",
            published_by="admin-legacy",
        )
    )

    artifact = service.export_domain_playbooks(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
    )

    adopted = repository.get_snapshot(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
        playbook_id="external_review",
        version="v3",
    )
    assert [playbook.id for playbook in artifact.playbooks] == ["external_review"]
    assert adopted is not None
    assert adopted.snapshot_id == "kb-playbooks:medicare_fraud:external_review:v3"
    assert adopted.definition.summary == "Migrated from the domain-only snapshot table."
    assert adopted.source == "api_import"


def test_import_rejects_conflicting_existing_snapshot() -> None:
    service = _service()
    service.import_playbooks(
        PlaybookImportArtifact(
            domain_name="medicare_fraud",
            catalog_version="external-v1",
            playbooks=[
                FraudPlaybookConfig(
                    id="external_review",
                    version="v3",
                    title="External Review",
                    summary="Original definition.",
                    status="draft",
                )
            ],
        ),
        knowledge_base_id=_KB_ID,
        actor_user_id="admin-2",
    )

    with pytest.raises(ValueError, match="already exists with different definition"):
        service.import_playbooks(
            PlaybookImportArtifact(
                domain_name="medicare_fraud",
                catalog_version="external-v1",
                playbooks=[
                    FraudPlaybookConfig(
                        id="external_review",
                        version="v3",
                        title="External Review",
                        summary="Conflicting definition.",
                        status="draft",
                    )
                ],
            ),
            knowledge_base_id=_KB_ID,
            actor_user_id="admin-3",
        )

    artifact = service.export_domain_playbooks(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
    )
    assert artifact.playbooks[0].summary == "Original definition."


def test_import_same_definition_is_idempotent() -> None:
    repository, service = _repository_service()
    artifact = PlaybookImportArtifact(
        domain_name="medicare_fraud",
        catalog_version="external-v1",
        playbooks=[
            FraudPlaybookConfig(
                id="external_review",
                version="v3",
                title="External Review",
                summary="Original definition.",
                status="draft",
            )
        ],
    )

    first = service.import_playbooks(
        artifact,
        knowledge_base_id=_KB_ID,
        actor_user_id="admin-2",
    )
    before = repository.get_snapshot(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
        playbook_id="external_review",
        version="v3",
    )
    second = service.import_playbooks(
        artifact,
        knowledge_base_id=_KB_ID,
        actor_user_id="admin-3",
    )
    after = repository.get_snapshot(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
        playbook_id="external_review",
        version="v3",
    )

    assert first.snapshot_ids == second.snapshot_ids
    assert before is not None and after is not None
    assert before.published_by == "admin-2"
    assert after.published_by == before.published_by
    assert after.source == before.source
    assert after.published_at == before.published_at
    assert after.created_at == before.created_at
    assert after.updated_at == before.updated_at
    exported = service.export_domain_playbooks(
        knowledge_base_id=_KB_ID,
        domain_name="medicare_fraud",
    )
    assert exported.playbooks[0].summary == "Original definition."


def test_import_rejects_conflicting_config_seed_snapshot() -> None:
    service = _service()

    with pytest.raises(ValueError, match="conflicts with config-authored seed"):
        service.import_playbooks(
            PlaybookImportArtifact(
                domain_name="medicare_fraud",
                catalog_version="external-v1",
                playbooks=[
                    FraudPlaybookConfig(
                        id="provider_billing_spike_review",
                        version="v1",
                        title="Conflicting Seed Review",
                        summary="Conflicts with the config-authored seed.",
                        status="draft",
                    )
                ],
            ),
            knowledge_base_id=_KB_ID,
            actor_user_id="admin-2",
        )


def test_import_rejects_artifact_without_partial_writes() -> None:
    repository, service = _repository_service()

    with pytest.raises(ValueError, match="conflicts with config-authored seed"):
        service.import_playbooks(
            PlaybookImportArtifact(
                domain_name="medicare_fraud",
                catalog_version="external-v1",
                playbooks=[
                    FraudPlaybookConfig(
                        id="external_review",
                        version="v3",
                        title="External Review",
                        summary="This should not be written.",
                        status="draft",
                    ),
                    FraudPlaybookConfig(
                        id="provider_billing_spike_review",
                        version="v1",
                        title="Conflicting Seed Review",
                        summary="Conflicts with the config-authored seed.",
                        status="draft",
                    ),
                ],
            ),
            knowledge_base_id=_KB_ID,
            actor_user_id="admin-2",
        )

    assert (
        repository.get_snapshot(
            knowledge_base_id=_KB_ID,
            domain_name="medicare_fraud",
            playbook_id="external_review",
            version="v3",
        )
        is None
    )


def test_import_rejects_unknown_references_without_partial_writes() -> None:
    repository, service = _repository_service()

    with pytest.raises(ValueError, match="references unknown feature_id 'missing_feature'"):
        service.import_playbooks(
            PlaybookImportArtifact(
                domain_name="medicare_fraud",
                catalog_version="external-v1",
                playbooks=[
                    FraudPlaybookConfig(
                        id="external_review",
                        version="v3",
                        title="External Review",
                        summary="This should not be written.",
                        status="draft",
                    ),
                    FraudPlaybookConfig(
                        id="bad_refs",
                        version="v1",
                        title="Bad Refs",
                        status="draft",
                        typology_ids=["missing_typology"],
                        feature_ids=["missing_feature"],
                        policy_rule_ids=["missing_pack.missing_rule"],
                    ),
                ],
            ),
            knowledge_base_id=_KB_ID,
            actor_user_id="admin-2",
        )

    assert (
        repository.get_snapshot(
            knowledge_base_id=_KB_ID,
            domain_name="medicare_fraud",
            playbook_id="external_review",
            version="v3",
        )
        is None
    )


def test_publish_seed_rejects_conflicting_existing_snapshot() -> None:
    repository, service = _repository_service()
    repository.upsert_snapshot(
        PlaybookSnapshot(
            snapshot_id="kb-playbooks:medicare_fraud:provider_billing_spike_review:v1",
            knowledge_base_id=_KB_ID,
            domain_name="medicare_fraud",
            playbook_id="provider_billing_spike_review",
            version="v1",
            status="published",
            source="api_import",
            definition=FraudPlaybookConfig(
                id="provider_billing_spike_review",
                version="v1",
                title="Conflicting Seed Review",
                summary="Conflicts with the config-authored seed.",
                status="published",
            ),
            published_by="admin-2",
        )
    )

    with pytest.raises(ValueError, match="already exists with different definition"):
        service.publish_config_playbook(
            PlaybookPublishRequest(
                knowledge_base_id=_KB_ID,
                domain_name="medicare_fraud",
                playbook_id="provider_billing_spike_review",
                version="v1",
                actor_user_id="admin-1",
            )
        )


def test_import_artifact_rejects_duplicate_playbook_versions() -> None:
    playbook = FraudPlaybookConfig(
        id="external_review",
        version="v3",
        title="External Review",
        status="draft",
    )

    with pytest.raises(ValidationError, match="playbook id/version pairs must be unique"):
        PlaybookImportArtifact(
            domain_name="medicare_fraud",
            catalog_version="external-v1",
            playbooks=[playbook, playbook],
        )


def test_import_artifact_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValidationError):
        PlaybookImportArtifact.model_validate(
            {
                "schema_version": "playbooks.v2",
                "domain_name": "medicare_fraud",
                "catalog_version": "external-v1",
                "playbooks": [],
            }
        )


def test_publish_unknown_seed_playbook_raises_key_error() -> None:
    service = _service()

    with pytest.raises(KeyError):
        service.publish_config_playbook(
            PlaybookPublishRequest(
                knowledge_base_id=_KB_ID,
                domain_name="medicare_fraud",
                playbook_id="missing",
                version="v1",
                actor_user_id="admin-1",
            )
        )
