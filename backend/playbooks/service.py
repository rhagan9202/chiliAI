"""Playbook publication, export, and import service."""

from __future__ import annotations

from config.schema import DomainConfig, FraudPlaybookConfig
from playbooks.models import (
    LEGACY_PLAYBOOK_KNOWLEDGE_BASE_ID,
    PlaybookImportArtifact,
    PlaybookImportResult,
    PlaybookPage,
    PlaybookPublishRequest,
    PlaybookSnapshot,
    PlaybookSnapshotSource,
)
from playbooks.repository import PlaybookRepository
from shared.utils import utc_now


class PlaybookService:
    """Coordinate config-authored playbooks with published snapshots."""

    def __init__(
        self, *, repository: PlaybookRepository, domain_config: DomainConfig
    ) -> None:
        self._repository = repository
        self._domain_config = domain_config

    def list_config_playbooks(
        self, *, domain_name: str, limit: int = 50, offset: int = 0
    ) -> PlaybookPage:
        self._require_active_domain(domain_name)
        definitions = [
            playbook.model_copy(deep=True)
            for playbook in self._domain_config.playbooks.items
        ]
        if limit <= 0 or offset < 0:
            items: list[FraudPlaybookConfig] = []
        else:
            items = definitions[offset : offset + limit]
        return PlaybookPage(
            items=items,
            total=len(definitions),
            limit=max(limit, 1),
            offset=max(offset, 0),
        )

    def get_config_playbook(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> FraudPlaybookConfig | None:
        """Return one config-authored playbook by natural key."""
        return self._find_config_playbook(
            domain_name=domain_name,
            playbook_id=playbook_id,
            version=version,
        )

    def publish_config_playbook(self, request: PlaybookPublishRequest) -> PlaybookSnapshot:
        self.adopt_legacy_snapshots(
            knowledge_base_id=request.knowledge_base_id,
            domain_name=request.domain_name,
        )
        definition = self._config_playbook_by_id(
            domain_name=request.domain_name,
            playbook_id=request.playbook_id,
            version=request.version,
        )
        snapshot = self._snapshot_from_definition(
            knowledge_base_id=request.knowledge_base_id,
            domain_name=request.domain_name,
            definition=definition,
            source="domain_config",
            actor_user_id=request.actor_user_id,
        )
        existing = self._repository.get_snapshot(
            knowledge_base_id=request.knowledge_base_id,
            domain_name=request.domain_name,
            playbook_id=request.playbook_id,
            version=request.version,
        )
        if existing is not None:
            if not _same_definition(existing.definition, snapshot.definition):
                raise ValueError(
                    f"Playbook snapshot '{snapshot.snapshot_id}' already exists "
                    "with different definition."
                )
            return existing

        return self._repository.upsert_snapshot(snapshot)

    def export_domain_playbooks(
        self, *, knowledge_base_id: str, domain_name: str
    ) -> PlaybookImportArtifact:
        self._require_active_domain(domain_name)
        self.adopt_legacy_snapshots(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
        )
        definitions = self._published_definitions(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
        )
        if not definitions:
            definitions = [
                playbook.model_copy(deep=True)
                for playbook in self._domain_config.playbooks.items
            ]

        return PlaybookImportArtifact(
            domain_name=domain_name,
            catalog_version=self._domain_config.playbooks.version,
            playbooks=definitions,
        )

    def import_playbooks(
        self,
        artifact: PlaybookImportArtifact,
        *,
        knowledge_base_id: str,
        actor_user_id: str,
    ) -> PlaybookImportResult:
        self._require_active_domain(artifact.domain_name)
        self.adopt_legacy_snapshots(
            knowledge_base_id=knowledge_base_id,
            domain_name=artifact.domain_name,
        )
        self._validate_import_references(artifact)
        snapshots = [
            self._snapshot_from_definition(
                knowledge_base_id=knowledge_base_id,
                domain_name=artifact.domain_name,
                definition=playbook,
                source="api_import",
                actor_user_id=actor_user_id,
            )
            for playbook in artifact.playbooks
        ]
        existing_by_snapshot_id: dict[str, PlaybookSnapshot] = {}
        for snapshot in snapshots:
            self._validate_import_snapshot(snapshot)
            existing = self._repository.get_snapshot(
                knowledge_base_id=snapshot.knowledge_base_id,
                domain_name=snapshot.domain_name,
                playbook_id=snapshot.playbook_id,
                version=snapshot.version,
            )
            if existing is not None:
                if not _same_definition(existing.definition, snapshot.definition):
                    raise ValueError(
                        f"Playbook snapshot '{snapshot.snapshot_id}' already exists "
                        "with different definition."
                    )
                existing_by_snapshot_id[snapshot.snapshot_id] = existing

        snapshot_ids: list[str] = []
        for snapshot in snapshots:
            existing = existing_by_snapshot_id.get(snapshot.snapshot_id)
            if existing is not None:
                snapshot_ids.append(existing.snapshot_id)
            else:
                stored = self._repository.upsert_snapshot(snapshot)
                snapshot_ids.append(stored.snapshot_id)

        return PlaybookImportResult(
            domain_name=artifact.domain_name,
            imported_count=len(snapshot_ids),
            snapshot_ids=snapshot_ids,
        )

    def adopt_legacy_snapshots(
        self, *, knowledge_base_id: str, domain_name: str
    ) -> int:
        """Copy old domain-scoped snapshots into one authorized KB scope."""
        self._require_active_domain(domain_name)
        if knowledge_base_id == LEGACY_PLAYBOOK_KNOWLEDGE_BASE_ID:
            return 0

        adopted_count = 0
        limit = 100
        offset = 0
        while True:
            page = self._repository.list_snapshots(
                knowledge_base_id=LEGACY_PLAYBOOK_KNOWLEDGE_BASE_ID,
                domain_name=domain_name,
                limit=limit,
                offset=offset,
            )
            for legacy_snapshot in page.items:
                existing = self._repository.get_snapshot(
                    knowledge_base_id=knowledge_base_id,
                    domain_name=domain_name,
                    playbook_id=legacy_snapshot.playbook_id,
                    version=legacy_snapshot.version,
                )
                if existing is not None:
                    continue
                adopted = legacy_snapshot.model_copy(
                    update={
                        "snapshot_id": (
                            f"{knowledge_base_id}:{domain_name}:"
                            f"{legacy_snapshot.playbook_id}:"
                            f"{legacy_snapshot.version}"
                        ),
                        "knowledge_base_id": knowledge_base_id,
                    },
                    deep=True,
                )
                self._repository.upsert_snapshot(adopted)
                adopted_count += 1
            offset += len(page.items)
            if offset >= page.total or not page.items:
                return adopted_count

    def _require_active_domain(self, domain_name: str) -> None:
        if self._domain_config.domain.name != domain_name:
            raise KeyError(domain_name)

    def _config_playbook_by_id(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> FraudPlaybookConfig:
        definition = self._find_config_playbook(
            domain_name=domain_name,
            playbook_id=playbook_id,
            version=version,
        )
        if definition is not None:
            return definition
        raise KeyError(f"{domain_name}:{playbook_id}:{version}")

    def _find_config_playbook(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> FraudPlaybookConfig | None:
        self._require_active_domain(domain_name)
        for playbook in self._domain_config.playbooks.items:
            if playbook.id == playbook_id and playbook.version == version:
                return playbook.model_copy(
                    update={"status": "published"},
                    deep=True,
                )
        return None

    def _validate_import_snapshot(self, snapshot: PlaybookSnapshot) -> None:
        definition = self._find_config_playbook(
            domain_name=snapshot.domain_name,
            playbook_id=snapshot.playbook_id,
            version=snapshot.version,
        )
        if definition is not None and not _same_definition(definition, snapshot.definition):
            raise ValueError(
                f"Imported playbook snapshot '{snapshot.snapshot_id}' conflicts "
                "with config-authored seed."
            )

    def _validate_import_references(self, artifact: PlaybookImportArtifact) -> None:
        errors: list[str] = []
        feature_ids = {feature.id for feature in self._domain_config.feature_catalog.features}
        typology_ids = {typology.id for typology in self._domain_config.typologies}
        policy_rule_ids = {
            f"{pack.id}.{rule.id}"
            for pack in self._domain_config.policy_rules
            for rule in pack.rules
        }
        for playbook in artifact.playbooks:
            for typology_id in playbook.typology_ids:
                if typology_id not in typology_ids:
                    errors.append(
                        f"Playbook '{playbook.id}' references unknown typology_id "
                        f"'{typology_id}'."
                    )
            for feature_id in playbook.feature_ids:
                if feature_id not in feature_ids:
                    errors.append(
                        f"Playbook '{playbook.id}' references unknown feature_id "
                        f"'{feature_id}'."
                    )
            for policy_rule_id in playbook.policy_rule_ids:
                if policy_rule_id not in policy_rule_ids:
                    errors.append(
                        f"Playbook '{playbook.id}' references unknown policy_rule_id "
                        f"'{policy_rule_id}'."
                    )
        if errors:
            raise ValueError("; ".join(errors))

    def _published_definitions(
        self, *, knowledge_base_id: str, domain_name: str
    ) -> list[FraudPlaybookConfig]:
        definitions: list[FraudPlaybookConfig] = []
        limit = 100
        offset = 0
        while True:
            page = self._repository.list_snapshots(
                knowledge_base_id=knowledge_base_id,
                domain_name=domain_name,
                limit=limit,
                offset=offset,
            )
            definitions.extend(
                snapshot.definition.model_copy(deep=True) for snapshot in page.items
            )
            offset += len(page.items)
            if offset >= page.total or not page.items:
                return definitions

    def _snapshot_from_definition(
        self,
        *,
        knowledge_base_id: str,
        domain_name: str,
        definition: FraudPlaybookConfig,
        source: PlaybookSnapshotSource,
        actor_user_id: str,
    ) -> PlaybookSnapshot:
        now = utc_now()
        published_definition = definition.model_copy(
            update={"status": "published"}, deep=True
        )
        return PlaybookSnapshot(
            snapshot_id=(
                f"{knowledge_base_id}:{domain_name}:{definition.id}:{definition.version}"
            ),
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            playbook_id=definition.id,
            version=definition.version,
            status="published",
            definition=published_definition,
            source=source,
            published_by=actor_user_id,
            published_at=now,
            created_at=now,
            updated_at=now,
        )


def _same_definition(
    left: FraudPlaybookConfig, right: FraudPlaybookConfig
) -> bool:
    return left.model_dump(mode="json") == right.model_dump(mode="json")
