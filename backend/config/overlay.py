"""Base + environment overlay layering for domain configuration (config.04).

Merge semantics (ADR 0001): mappings deep-merge with overlay keys winning
recursively; lists and scalars replace wholesale; an explicit ``null`` in an
overlay sets the field to ``None``. There are no key-removal semantics —
absence falls through to the base value or the schema default.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeGuard

logger = logging.getLogger(__name__)


def _is_mapping(value: object) -> TypeGuard[dict[str, Any]]:
    """Narrow ``value`` to ``dict[str, Any]`` for pyright-strict recursion."""
    return isinstance(value, dict)


def merge_config_layers(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Return ``base`` with ``overlay`` layered on top (pure; inputs untouched)."""

    merged: dict[str, Any] = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if _is_mapping(base_value) and _is_mapping(overlay_value):
            merged[key] = merge_config_layers(base_value, overlay_value)
        else:
            merged[key] = overlay_value
    return merged


OVERLAY_FOR_KEY = "overlay_for"


class OverlayError(Exception):
    """Raised when an overlay file is structurally invalid."""


def known_top_level_keys() -> set[str]:
    from config.schema import DomainConfig  # local import: avoid import cycles

    return set(DomainConfig.model_fields) | {OVERLAY_FOR_KEY}


def apply_overlays(
    base_data: dict[str, Any],
    overlay_paths: list[Path],
    *,
    parse: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    """Layer each overlay onto ``base_data`` in declared order.

    An overlay whose ``overlay_for`` does not match the base's
    ``domain.name`` is skipped with a warning (hot-swap safety — see ADR
    0001); a missing ``overlay_for`` or an unknown top-level key raises
    ``OverlayError``.
    """

    base_domain = base_data.get("domain", {})
    if not _is_mapping(base_domain):
        base_name: str | None = None
    else:
        base_name = base_domain.get("name")
    merged = base_data
    known_keys_set = known_top_level_keys()
    for path in overlay_paths:
        overlay = parse(path)
        if OVERLAY_FOR_KEY not in overlay:
            raise OverlayError(
                f"Overlay {path} is missing the required '{OVERLAY_FOR_KEY}' key."
            )
        unknown = sorted(set(overlay) - known_keys_set)
        if unknown:
            raise OverlayError(
                f"Overlay {path} contains unknown top-level keys {unknown}. "
                "Valid keys are the DomainConfig sections plus 'overlay_for'."
            )
        target = overlay[OVERLAY_FOR_KEY]
        if target != base_name:
            logger.warning(
                "Skipping overlay %s: overlay_for=%r does not match base "
                "domain.name=%r (hot-swap safety, ADR 0001).",
                path,
                target,
                base_name,
            )
            continue
        payload = {k: v for k, v in overlay.items() if k != OVERLAY_FOR_KEY}
        merged = merge_config_layers(merged, payload)
    return merged


__all__ = [
    "OverlayError",
    "apply_overlays",
    "known_top_level_keys",
    "merge_config_layers",
]
