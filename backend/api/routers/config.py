"""Configuration API router — serves domain config to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_domain_config_payload

__all__ = ["router"]

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/domain")
async def get_domain(
    config: dict[str, object] = Depends(get_domain_config_payload),
) -> dict[str, object]:
    """Return the active domain configuration."""
    return config
