"""Load and validate domain configuration from YAML or JSON files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from config.schema import DomainConfig


class ConfigLoadError(Exception):
    """Raised when domain configuration cannot be loaded or validated."""


def load_config(path: str | Path | None = None) -> DomainConfig:
    """Load a domain configuration file and return a validated ``DomainConfig``.

    Resolution order for the config file path:
    1. Explicit ``path`` argument.
    2. ``CHILI_CONFIG_PATH`` environment variable.

    Raises ``ConfigLoadError`` on file-not-found, parse errors, or
    schema validation failures.
    """
    resolved = _resolve_path(path)

    raw = _read_file(resolved)
    data = _parse_content(raw, resolved)
    return _validate(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)

    env_path = os.environ.get("CHILI_CONFIG_PATH")
    if env_path:
        return Path(env_path)

    raise ConfigLoadError(
        "No config path provided and CHILI_CONFIG_PATH is not set."
    )


def _read_file(path: Path) -> str:
    if not path.is_file():
        raise ConfigLoadError(f"Config file not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(f"Cannot read config file {path}: {exc}") from exc


def _parse_content(raw: str, path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(raw)
        elif suffix == ".json":
            data = json.loads(raw)
        else:
            raise ConfigLoadError(
                f"Unsupported config file extension '{suffix}'. "
                "Use .yaml, .yml, or .json."
            )
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"YAML parse error in {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(f"JSON parse error in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigLoadError(
            f"Config file {path} must contain a mapping at the top level."
        )
    return data


def _validate(data: dict[str, Any]) -> DomainConfig:
    try:
        return DomainConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(
            f"Config validation failed:\n{exc}"
        ) from exc
