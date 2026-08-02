"""Domain-config-backed feature catalog service."""

from __future__ import annotations

from config.schema import DomainConfig, FeatureCatalogConfig, FraudTypologyConfig


class FeatureCatalogService:
    """Read feature catalog metadata from the active domain configuration."""

    def __init__(self, config: DomainConfig) -> None:
        self._config = config

    def get_catalog(self) -> FeatureCatalogConfig:
        """Return the active domain's versioned feature catalog."""

        return self._config.feature_catalog

    def list_typologies(self) -> list[FraudTypologyConfig]:
        """Return configured fraud typologies for the active domain."""

        return list(self._config.typologies)

    def list_entity_values(
        self,
        *,
        knowledge_base_id: str,
        entity_type: str,
        entity_id: str,
    ) -> list[object]:
        """Return normalized feature values for an entity.

        Sprint 1 exposes the read contract and catalog metadata. Durable feature
        value persistence is introduced by the next task, so this method returns
        an empty list while preserving the eventual service boundary.
        """

        del knowledge_base_id, entity_type, entity_id
        return []


def create_feature_catalog_service(config: DomainConfig) -> FeatureCatalogService:
    """Construct the config-backed feature catalog service."""

    return FeatureCatalogService(config)
