"""Projection read models for queryable risk surfaces."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

from shared.utils import utc_now

RiskProjectionLevel = Literal["low", "medium", "high", "critical"]
RiskProjectionStatus = Literal["active", "case_open", "resolved", "suppressed", "stale"]


class RiskProjectionRow(BaseModel):
    """Latest risk read model for one entity in one knowledge base."""

    knowledge_base_id: str
    entity_id: str
    entity_type: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: RiskProjectionLevel
    top_typology_ids: list[str] = Field(default_factory=list[str])
    alert_ids: list[str] = Field(default_factory=list[str])
    case_ids: list[str] = Field(default_factory=list[str])
    evidence_pack_ids: list[str] = Field(default_factory=list[str])
    score_run_id: str | None = None
    model_version: str
    catalog_version: str
    scored_at: datetime
    updated_at: datetime = Field(default_factory=utc_now)
    status: RiskProjectionStatus = "active"

    @field_validator("scored_at", "updated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Risk projection timestamps must be timezone-aware.")
        return value


class RiskProjectionQuery(BaseModel):
    """Filters for ranked risk projection reads."""

    knowledge_base_id: str
    entity_type: str | None = None
    risk_level: RiskProjectionLevel | None = None
    typology_id: str | None = None
    status: RiskProjectionStatus | None = None
    max_score_age_hours: int | None = Field(default=None, gt=0)
    as_of: datetime = Field(default_factory=utc_now)
    limit: int = Field(default=20, gt=0, le=500)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _require_age_clock(self) -> RiskProjectionQuery:
        if self.max_score_age_hours is not None and self.as_of.tzinfo is None:
            raise ValueError("RiskProjectionQuery.as_of must be timezone-aware.")
        return self


class RiskProjectionPage(BaseModel):
    """Page of ranked risk projection rows."""

    items: list[RiskProjectionRow] = Field(default_factory=list[RiskProjectionRow])
    total: int = Field(ge=0)
    limit: int = Field(ge=0)
    offset: int = Field(ge=0)


@runtime_checkable
class RiskProjectionRepositoryProtocol(Protocol):
    """Persistence protocol for risk projection read models."""

    def upsert(self, row: RiskProjectionRow) -> RiskProjectionRow: ...

    def get(self, knowledge_base_id: str, entity_id: str) -> RiskProjectionRow | None: ...

    def list(self, query: RiskProjectionQuery) -> RiskProjectionPage: ...

    def list_all(self, knowledge_base_id: str) -> list[RiskProjectionRow]: ...

    def delete_by_kb(self, knowledge_base_id: str) -> int: ...


class InMemoryRiskProjectionRepository:
    """In-memory projection repository for tests and local development."""

    def __init__(self, rows: list[RiskProjectionRow] | None = None) -> None:
        self._rows: dict[tuple[str, str], RiskProjectionRow] = {}
        for row in rows or []:
            self.upsert(row)

    def upsert(self, row: RiskProjectionRow) -> RiskProjectionRow:
        stored = row.model_copy(deep=True)
        self._rows[(stored.knowledge_base_id, stored.entity_id)] = stored
        return stored.model_copy(deep=True)

    def get(self, knowledge_base_id: str, entity_id: str) -> RiskProjectionRow | None:
        row = self._rows.get((knowledge_base_id, entity_id))
        return row.model_copy(deep=True) if row is not None else None

    def list(self, query: RiskProjectionQuery) -> RiskProjectionPage:
        rows = [
            row
            for row in self._rows.values()
            if _matches(row, query)
        ]
        rows.sort(key=lambda row: (-row.overall_score, -row.scored_at.timestamp(), row.entity_id))
        total = len(rows)
        items = rows[query.offset : query.offset + query.limit]
        return RiskProjectionPage(
            items=[row.model_copy(deep=True) for row in items],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    def list_all(self, knowledge_base_id: str) -> list[RiskProjectionRow]:
        rows = [
            row
            for row in self._rows.values()
            if row.knowledge_base_id == knowledge_base_id
        ]
        rows.sort(key=lambda row: (-row.overall_score, -row.scored_at.timestamp(), row.entity_id))
        return [row.model_copy(deep=True) for row in rows]

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [
            key
            for key in self._rows
            if key[0] == knowledge_base_id
        ]
        for key in keys:
            del self._rows[key]
        return len(keys)


def _matches(row: RiskProjectionRow, query: RiskProjectionQuery) -> bool:
    if row.knowledge_base_id != query.knowledge_base_id:
        return False
    if query.entity_type is not None and row.entity_type != query.entity_type:
        return False
    if query.risk_level is not None and row.risk_level != query.risk_level:
        return False
    if query.typology_id is not None and query.typology_id not in row.top_typology_ids:
        return False
    if query.status is not None and row.status != query.status:
        return False
    if query.max_score_age_hours is not None:
        cutoff = query.as_of - timedelta(hours=query.max_score_age_hours)
        if row.scored_at < cutoff:
            return False
    return True


__all__ = [
    "InMemoryRiskProjectionRepository",
    "RiskProjectionLevel",
    "RiskProjectionPage",
    "RiskProjectionQuery",
    "RiskProjectionRepositoryProtocol",
    "RiskProjectionRow",
    "RiskProjectionStatus",
]
