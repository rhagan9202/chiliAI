"""Domain configuration — schema, loader, and validation.

Parses YAML/JSON domain configuration files into typed Pydantic models
and validates cross-field constraints (relationship references,
uniqueness, enum requirements).
"""

from config.loader import ConfigLoadError, load_config
from config.schema import DomainConfig

__all__ = [
    "ConfigLoadError",
    "DomainConfig",
    "load_config",
]
