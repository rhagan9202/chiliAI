"""Base + environment overlay layering for domain configuration (config.04).

Merge semantics (ADR 0001): mappings deep-merge with overlay keys winning
recursively; lists and scalars replace wholesale; an explicit ``null`` in an
overlay sets the field to ``None``. There are no key-removal semantics —
absence falls through to the base value or the schema default.
"""

from __future__ import annotations

from typing import Any


def merge_config_layers(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Return ``base`` with ``overlay`` layered on top (pure; inputs untouched)."""

    merged: dict[str, Any] = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = merge_config_layers(
                base_value, overlay_value
            )
        else:
            merged[key] = overlay_value
    return merged


__all__ = ["merge_config_layers"]
