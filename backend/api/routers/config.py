"""Configuration API router — serves domain config to the frontend."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_domain_config
from config.schema import DomainConfig

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/domain")
async def get_domain(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, Any]:
    """Return the active domain configuration."""
    return config.model_dump()
