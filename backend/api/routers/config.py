"""Configuration API router — serves domain config to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_domain_config_payload

__all__ = ["router"]

router = APIRouter(prefix="/config", tags=["configuration"])

# TODO(production): Add config management endpoints:
# - POST /config/domain — update config (with validation)
# - GET /config/domain/schema — return JSON Schema for frontend form generation
# - POST /config/reload — force reload from disk
# - GET /config/features — feature flags derived from capabilities
# Add ETag / Last-Modified headers for caching. Add change audit logging.


@router.get("/domain")
async def get_domain(
    config: dict[str, object] = Depends(get_domain_config_payload),
) -> dict[str, object]:
    """Return the active domain configuration."""
    return config
