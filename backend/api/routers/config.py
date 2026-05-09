"""Configuration API router — serves domain config and feature metadata to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import (
    get_domain_config_features_payload,
    get_domain_config_payload,
    get_domain_config_schema_payload,
)

__all__ = ["router"]

router = APIRouter(prefix="/config", tags=["configuration"])

# TODO(production): Add config management endpoints:
# - POST /config/domain — update config (with validation)
# - POST /config/reload — force reload from disk
# Add ETag / Last-Modified headers for caching. Add change audit logging.


@router.get("/domain")
async def get_domain(
    config: dict[str, object] = Depends(get_domain_config_payload),
) -> dict[str, object]:
    """Return the active domain configuration."""
    return config


@router.get("/features")
async def get_features(
    features: dict[str, object] = Depends(get_domain_config_features_payload),
) -> dict[str, object]:
    """Return feature flags and enabled page metadata for the frontend."""
    return features


@router.get("/domain/schema")
async def get_domain_schema(
    schema: dict[str, object] = Depends(get_domain_config_schema_payload),
) -> dict[str, object]:
    """Return the JSON schema for the domain configuration model."""
    return schema
