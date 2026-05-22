"""Coercion and feed-schema validation for submitted record rows.

Row validation reuses :func:`shared.types.validate_entity` by treating a feed
``record_schema`` as a synthetic ``EntityDefinition`` — this keeps a single
source of truth for property type / range / pattern checks.
"""

from __future__ import annotations

from collections.abc import Mapping

from config.schema import RecordFeedConfig
from records.exceptions import RecordValidationError
from shared.types import (
    Entity,
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    validate_entity,
)

_TRUE_TOKENS = frozenset({"true", "1", "yes"})
_FALSE_TOKENS = frozenset({"false", "0", "no"})


def _coerce_value(value: object, property_type: PropertyType) -> object:
    """Coerce a string-encoded value to the declared property type.

    Non-string values pass through untouched (JSON sources are already typed).
    For DATE fields, bare 8-digit YYYYMMDD strings are normalised to ISO-8601
    (YYYY-MM-DD) so that downstream validators can accept them.
    """

    if not isinstance(value, str):
        return value
    text = value.strip()
    if property_type is PropertyType.DATE:
        # Accept YYYYMMDD (e.g. CMS DE-SynPUF) and convert to YYYY-MM-DD.
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return text
    if property_type is PropertyType.INTEGER:
        try:
            return int(text)
        except ValueError as exc:
            raise RecordValidationError(f"Value '{value}' is not a valid integer.") from exc
    if property_type is PropertyType.DECIMAL:
        try:
            return float(text)
        except ValueError as exc:
            raise RecordValidationError(f"Value '{value}' is not a valid number.") from exc
    if property_type is PropertyType.BOOLEAN:
        lowered = text.lower()
        if lowered in _TRUE_TOKENS:
            return True
        if lowered in _FALSE_TOKENS:
            return False
        raise RecordValidationError(f"Value '{value}' is not a valid boolean.")
    return value


def coerce_row(
    row: Mapping[str, object], schema: dict[str, PropertyDefinition]
) -> dict[str, object]:
    """Return a copy of ``row`` with values coerced to their declared types.

    Empty strings for non-required typed fields are treated as absent: the key
    is dropped from the coerced row so downstream validators do not attempt to
    parse ``""`` as a date, integer, or decimal.  Empty strings for required
    fields are kept so that the required-field check in ``validate_entity``
    fires correctly.
    """

    coerced: dict[str, object] = {}
    for key, value in row.items():
        definition = schema.get(key)
        if (
            definition is not None
            and isinstance(value, str)
            and value.strip() == ""
            and not definition.required
        ):
            # Drop absent optional typed fields — e.g. BENE_DEATH_DT="" for
            # living beneficiaries in CMS DE-SynPUF exports.
            continue
        coerced[key] = value if definition is None else _coerce_value(value, definition.type)
    return coerced


def validate_rows(
    feed: RecordFeedConfig, rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Coerce and validate every row against the feed schema.

    Returns the coerced rows on success; raises :class:`RecordValidationError`
    listing every offending row when any row fails.

    When ``feed.allow_extra_fields`` is ``True``, columns not declared in
    ``record_schema`` are passed through to the stored payload but are excluded
    from entity validation.  This supports wide real-world files (e.g. CMS
    DE-SynPUF carrier claims with 142 columns) where only a subset of fields
    need to be typed and validated.
    """

    definition = EntityDefinition(
        name=feed.record_type,
        display_label=feed.record_type,
        icon="record",
        properties=feed.record_schema,
    )
    coerced_rows: list[dict[str, object]] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        try:
            coerced = coerce_row(row, feed.record_schema)
        except RecordValidationError as exc:
            errors.append(f"row {index}: {exc}")
            continue
        coerced_rows.append(coerced)
        # When allow_extra_fields is set, only the declared-schema properties
        # are passed to the entity validator so extra columns do not trigger
        # "Unexpected property" errors.
        entity_props: dict[str, object] = (
            {k: coerced[k] for k in feed.record_schema if k in coerced}
            if feed.allow_extra_fields
            else coerced
        )
        row_errors = validate_entity(
            Entity(id=f"row-{index}", type=feed.record_type, properties=entity_props),
            [definition],
        )
        if row_errors:
            errors.append(f"row {index}: " + "; ".join(row_errors))
    if errors:
        raise RecordValidationError(
            f"Feed '{feed.name}' validation failed:\n  - " + "\n  - ".join(errors)
        )
    return coerced_rows


__all__ = [
    "coerce_row",
    "validate_rows",
]
