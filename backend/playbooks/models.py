"""Domain-neutral fraud playbook models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from config.schema import FraudPlaybookConfig
from shared.utils import utc_now

PlaybookStatus = Literal["draft", "published", "retired"]
PlaybookSnapshotSource = Literal["domain_config", "api_import", "api_publish"]


class PlaybookSnapshot(BaseModel):
    """Immutable published playbook version."""

    snapshot_id: str = Field(min_length=1)
    domain_name: str = Field(min_length=1)
    playbook_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: PlaybookStatus = "published"
    definition: FraudPlaybookConfig
    source: PlaybookSnapshotSource = "domain_config"
    published_by: str = Field(min_length=1)
    published_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PlaybookPage(BaseModel):
    """One page of config-authored playbook definitions."""

    items: list[FraudPlaybookConfig] = Field(
        default_factory=lambda: cast(list[FraudPlaybookConfig], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class PlaybookSnapshotPage(BaseModel):
    """One page of published playbook snapshots."""

    items: list[PlaybookSnapshot] = Field(
        default_factory=lambda: cast(list[PlaybookSnapshot], [])
    )
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class PlaybookPublishRequest(BaseModel):
    """Request to publish a config-authored seed playbook."""

    domain_name: str = Field(min_length=1)
    playbook_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    actor_user_id: str = Field(min_length=1)


class PlaybookImportArtifact(BaseModel):
    """Portable artifact containing validated domain playbooks."""

    schema_version: Literal["playbooks.v1"] = "playbooks.v1"
    domain_name: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    playbooks: list[FraudPlaybookConfig] = Field(
        default_factory=lambda: cast(list[FraudPlaybookConfig], [])
    )

    @model_validator(mode="after")
    def _validate_unique_playbook_versions(self) -> PlaybookImportArtifact:
        pairs = [(playbook.id, playbook.version) for playbook in self.playbooks]
        if len(set(pairs)) != len(pairs):
            raise ValueError(
                "PlaybookImportArtifact playbook id/version pairs must be unique."
            )
        return self


class PlaybookImportResult(BaseModel):
    """Import result summary."""

    domain_name: str = Field(min_length=1)
    imported_count: int = Field(ge=0)
    snapshot_ids: list[str] = Field(default_factory=lambda: cast(list[str], []))


class PlaybookRef(BaseModel):
    """Historical reference to a playbook version."""

    playbook_id: str = Field(min_length=1)
    playbook_version: str = Field(min_length=1)
    title: str = ""


__all__ = [
    "PlaybookImportArtifact",
    "PlaybookImportResult",
    "PlaybookPage",
    "PlaybookPublishRequest",
    "PlaybookRef",
    "PlaybookSnapshot",
    "PlaybookSnapshotPage",
    "PlaybookSnapshotSource",
    "PlaybookStatus",
]
