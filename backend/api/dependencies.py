"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

from functools import lru_cache

from config.loader import load_config
from config.schema import DomainConfig


@lru_cache(maxsize=1)
def get_domain_config() -> DomainConfig:
    """Load and cache the domain configuration (singleton).

    The config is loaded once on first call and cached for the lifetime
    of the process.  To reload, restart the server.
    """
    return load_config()
