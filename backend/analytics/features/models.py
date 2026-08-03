"""Models for normalized analytics feature values."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from shared.utils import utc_now


class FeatureValueRecord(BaseModel):
    """A normalized feature observation for one entity."""

    knowledge_base_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    value: str | int | float | bool | None = None
    normalized_value: float | None = Field(default=None, ge=0.0, le=1.0)
    catalog_version: str = Field(min_length=1)
    transformation_version: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=utc_now)
    score_run_id: str | None = None

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, observed_at: datetime) -> datetime:
        """Normalize timestamps so repositories can sort observations consistently."""
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return observed_at.replace(tzinfo=timezone.utc)
        return observed_at.astimezone(timezone.utc)


__all__ = ["FeatureValueRecord"]
