"""Load and validate domain configuration from YAML or JSON files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

import yaml
from pydantic import JsonValue, ValidationError

from config.overlay import OverlayError, apply_overlays
from config.schema import DomainConfig
from config.store import ActivePackStoreError, resolve_config_path


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
    # TODO(production): Add secrets resolution for ${ENV_VAR} placeholders in
    # config values. Cache the loaded DomainConfig and support hot-reload via
    # file watcher or API endpoint. See docs/archive/config_engine_plan.md for
    # the historical config engine plan.
    resolved = _resolve_path(path)

    raw = _read_file(resolved)
    data = _parse_content(raw, resolved)
    overlay_paths = overlay_paths_from_env()
    if overlay_paths:
        try:
            data = apply_overlays(
                data, overlay_paths, base_path=resolved, parse=_parse_config_file
            )
        except OverlayError as exc:
            raise ConfigLoadError(str(exc)) from exc
    return _validate(data)


def load_active_config() -> DomainConfig:
    """Load the domain configuration for the *active* pack.

    Unlike :func:`load_config` (which stays pure: explicit path > env > error),
    this follows the file-backed active-pack pointer written by the config
    API on hot-swap: pointer > ``CHILI_CONFIG_PATH`` env > error. The worker
    uses this when rebuilding its dependencies on a ``config.updated`` event
    so it picks up the pack the API activated through the shared volume.

    Raises ``ConfigLoadError`` (store resolution failures are re-raised as
    ``ConfigLoadError``).
    """
    try:
        resolved = resolve_config_path()
    except ActivePackStoreError as exc:
        raise ConfigLoadError(str(exc)) from exc
    return load_config(resolved)


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


def _parse_content(raw: str, path: Path) -> dict[str, JsonValue]:
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
    return cast(dict[str, JsonValue], data)


def overlay_paths_from_env() -> list[Path]:
    """Overlay paths from `CHILI_CONFIG_OVERLAY_PATH`, in declaration order.

    Public because `api/routers/config.py` needs the same parsing to preview a
    candidate pack with overlays applied. Importing it as a private `_helper`
    across the module boundary is a `reportPrivateUsage` error, and duplicating
    the split logic would let the preview drift from what `load_config` does.
    """

    raw = os.environ.get("CHILI_CONFIG_OVERLAY_PATH", "")
    return [Path(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_config_file(path: Path) -> dict[str, JsonValue]:
    return _parse_content(_read_file(path), path)


def _validate(data: dict[str, JsonValue]) -> DomainConfig:
    try:
        return DomainConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(
            f"Config validation failed:\n{exc}"
        ) from exc


__all__ = [
    "ConfigLoadError",
    "load_active_config",
    "load_config",
    "overlay_paths_from_env",
]
