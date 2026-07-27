"""Config-driven display text for domain entities.

One resolution rule, shared by every producer of a user-facing entity name, so
the alert feed, the workbench, a case title and the chat context rail cannot
disagree about what an entity is called (UXA-304). The frontend implements the
identical ladder in ``chili_app/src/utils/domainDisplay.ts``; change both
together.
"""

from __future__ import annotations

from config.schema import DomainConfig
from shared.types import Entity

__all__ = ["entity_display_label"]


def _text(value: object | None) -> str | None:
    """Non-blank string form of a property value, or ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def entity_display_label(entity: Entity, config: DomainConfig) -> str:
    """Human name for ``entity`` under the active domain configuration.

    The ladder is: the configured ``ui.display_fields[type].title`` property,
    then a ``name`` property, then the entity type's display label plus its id.
    The last rung is deliberately not a bare id — an id alone reads as an
    internal handle, which is what UXA-304 was filed about.
    """

    display_fields = config.ui.display_fields if config.ui is not None else {}
    title_field = display_fields.get(entity.type)
    if title_field is not None:
        titled = _text(entity.properties.get(title_field.title))
        if titled is not None:
            return titled

    named = _text(entity.properties.get("name"))
    if named is not None:
        return named

    definition = next(
        (candidate for candidate in config.entities if candidate.name == entity.type),
        None,
    )
    type_label = definition.display_label if definition is not None else entity.type
    return f"{type_label} {entity.id}"
