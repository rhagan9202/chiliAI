"""Writer/rebuild service for risk projection read models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from analytics.features.models import FeatureValueRecord
from analytics.risk.projections import (
    RiskProjectionRepositoryProtocol,
    RiskProjectionRow,
    RiskProjectionStatus,
)
from events.types import RiskScoredReference


class RiskProjectionWriteRequest(BaseModel):
    """Inputs needed to write one risk projection row."""

    assessment: RiskScoredReference
    entity_type: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    scored_at: datetime
    score_run_id: str | None = None
    feature_values: list[FeatureValueRecord] = Field(default_factory=list[FeatureValueRecord])
    feature_typology_index: dict[str, list[str]] = Field(default_factory=dict)
    alert_ids: list[str] = Field(default_factory=list[str])
    case_ids: list[str] = Field(default_factory=list[str])
    evidence_pack_ids: list[str] = Field(default_factory=list[str])
    status: RiskProjectionStatus = "active"


@dataclass(frozen=True)
class RiskProjectionWriteResult:
    """Outcome for one projection write."""

    row: RiskProjectionRow
    changed: bool
    created: bool


@dataclass(frozen=True)
class RiskProjectionRebuildResult:
    """Outcome for a KB-scoped projection rebuild."""

    changed: bool
    deleted: int
    upserted: int


@runtime_checkable
class RiskProjectionRebuildSourceProtocol(Protocol):
    """Loads the authoritative projection rows for a KB rebuild."""

    def load_projection_rows(self, knowledge_base_id: str) -> Sequence[RiskProjectionRow]: ...


class RiskProjectionService:
    """Build and persist queryable risk projection rows."""

    def __init__(self, repository: RiskProjectionRepositoryProtocol) -> None:
        self._repository = repository

    def project_assessment(
        self,
        request: RiskProjectionWriteRequest,
    ) -> RiskProjectionWriteResult:
        """Upsert the read model for one risk assessment."""

        row = _row_from_request(request)
        existing = self._repository.get(row.knowledge_base_id, row.entity_id)
        if existing == row:
            return RiskProjectionWriteResult(row=existing, changed=False, created=False)
        stored = self._repository.upsert(row)
        return RiskProjectionWriteResult(
            row=stored,
            changed=True,
            created=existing is None,
        )

    def rebuild_knowledge_base(
        self,
        knowledge_base_id: str,
        rows: Sequence[RiskProjectionRow],
    ) -> RiskProjectionRebuildResult:
        """Replace all projection rows for one KB unless the projection is unchanged."""

        incoming = {
            row.entity_id: row
            for row in rows
            if row.knowledge_base_id == knowledge_base_id
        }
        existing = {
            row.entity_id: row
            for row in self._repository.list_all(knowledge_base_id)
        }
        if existing == incoming:
            return RiskProjectionRebuildResult(changed=False, deleted=0, upserted=0)

        deleted = self._repository.delete_by_kb(knowledge_base_id)
        for row in incoming.values():
            self._repository.upsert(row)
        return RiskProjectionRebuildResult(
            changed=True,
            deleted=deleted,
            upserted=len(incoming),
        )


def _row_from_request(request: RiskProjectionWriteRequest) -> RiskProjectionRow:
    assessment = request.assessment
    return RiskProjectionRow(
        knowledge_base_id=assessment.knowledge_base_id,
        entity_id=assessment.entity_id,
        entity_type=request.entity_type,
        overall_score=assessment.overall_score,
        risk_level=assessment.risk_level,
        top_typology_ids=_typology_ids_for_entity(
            assessment=assessment,
            entity_type=request.entity_type,
            feature_values=request.feature_values,
            feature_typology_index=request.feature_typology_index,
        ),
        alert_ids=_unique_sorted(request.alert_ids),
        case_ids=_unique_sorted(request.case_ids),
        evidence_pack_ids=_unique_sorted(request.evidence_pack_ids),
        score_run_id=request.score_run_id,
        model_version=request.model_version,
        catalog_version=request.catalog_version,
        scored_at=request.scored_at,
        updated_at=request.scored_at,
        status=request.status,
    )


def _typology_ids_for_entity(
    *,
    assessment: RiskScoredReference,
    entity_type: str,
    feature_values: Sequence[FeatureValueRecord],
    feature_typology_index: Mapping[str, Sequence[str]],
) -> list[str]:
    typology_ids: set[str] = set()
    scored_feature_names = {factor.factor_name for factor in assessment.factors}
    for value in feature_values:
        if (
            value.knowledge_base_id != assessment.knowledge_base_id
            or value.entity_id != assessment.entity_id
            or value.entity_type != entity_type
            or value.feature_id not in scored_feature_names
        ):
            continue
        typology_ids.update(feature_typology_index.get(value.feature_id, ()))
    return sorted(typology_ids)


def _unique_sorted(values: Sequence[str]) -> list[str]:
    return sorted(set(values))


__all__ = [
    "RiskProjectionRebuildResult",
    "RiskProjectionRebuildSourceProtocol",
    "RiskProjectionService",
    "RiskProjectionWriteRequest",
    "RiskProjectionWriteResult",
]
