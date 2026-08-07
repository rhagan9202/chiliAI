"""Coercion and feed-schema validation for submitted record rows.

Row validation reuses :func:`shared.types.validate_entity` by treating a feed
``record_schema`` as a synthetic ``EntityDefinition`` — this keeps a single
source of truth for property type / range / pattern checks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime

from config.schema import RecordFeedConfig
from records.exceptions import RecordValidationError
from records.models import RejectedRow
from shared.types import (
    Entity,
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    validate_entity,
)

_TRUE_TOKENS = frozenset({"true", "1", "yes"})
_FALSE_TOKENS = frozenset({"false", "0", "no"})

# Matches M/D/YYYY or MM/DD/YYYY (zero-padded or single-digit month/day).
_MMDDYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _coerce_value(value: object, property_type: PropertyType) -> object:
    """Coerce a string-encoded value to the declared property type.

    Non-string values pass through untouched (JSON sources are already typed).
    For DATE fields the following formats are normalised to ISO-8601
    (YYYY-MM-DD) so that downstream validators can accept them:

    * ``YYYYMMDD`` — 8-digit compact form used by CMS DE-SynPUF.
    * ``MM/DD/YYYY`` or ``M/D/YYYY`` — slash-delimited form used by CMS NPPES.
    """

    if not isinstance(value, str):
        return value
    text = value.strip()
    if property_type is PropertyType.DATE:
        # Accept YYYYMMDD (e.g. CMS DE-SynPUF) and convert to YYYY-MM-DD.
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        # Accept MM/DD/YYYY or M/D/YYYY (e.g. CMS NPPES) and convert to YYYY-MM-DD.
        match = _MMDDYYYY_RE.match(text)
        if match is not None:
            month_str, day_str, year_str = match.groups()
            try:
                normalized = datetime(
                    int(year_str), int(month_str), int(day_str)
                ).date()
            except ValueError as exc:
                raise RecordValidationError(
                    f"Value '{value}' is not a valid M/D/YYYY date."
                ) from exc
            return normalized.isoformat()
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


def validate_rows_partition(
    feed: RecordFeedConfig, rows: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[RejectedRow]]:
    """Coerce and validate every row, partitioning valid from invalid.

    Returns a ``(coerced_ok, rejected)`` tuple — valid rows are coerced and
    returned for ingestion, while each offending row is captured as a
    :class:`~records.models.RejectedRow` carrying its submission index and the
    failure reason.  Unlike :func:`validate_rows`, this never raises on
    individual bad rows, so a submission can ingest its good rows and report
    the bad ones.

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
    rejected: list[RejectedRow] = []
    for index, row in enumerate(rows):
        try:
            coerced = coerce_row(row, feed.record_schema)
        except RecordValidationError as exc:
            rejected.append(RejectedRow(index=index, reason=str(exc)))
            continue
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
            rejected.append(RejectedRow(index=index, reason="; ".join(row_errors)))
            continue
        coerced_rows.append(coerced)
    return coerced_rows, rejected


def validate_rows(
    feed: RecordFeedConfig, rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Coerce and validate every row against the feed schema.

    Returns the coerced rows on success; raises :class:`RecordValidationError`
    listing every offending row when any row fails.  This all-or-nothing variant
    is retained for callers that require a hard failure on any bad row; the
    service path uses :func:`validate_rows_partition` instead.

    When ``feed.allow_extra_fields`` is ``True``, columns not declared in
    ``record_schema`` are passed through to the stored payload but are excluded
    from entity validation.
    """

    coerced_rows, rejected = validate_rows_partition(feed, rows)
    if rejected:
        errors = [f"row {item.index}: {item.reason}" for item in rejected]
        raise RecordValidationError(
            f"Feed '{feed.name}' validation failed:\n  - " + "\n  - ".join(errors)
        )
    return coerced_rows


def derive_record_id(feed: RecordFeedConfig, row: Mapping[str, object]) -> str:
    """Return the record id for ``row`` under ``feed``'s id rules.

    Raises :class:`~records.exceptions.RecordValidationError` when the row
    cannot supply one. Extracted from ``RecordsService.register_records`` so
    that a caller which must *partition* rows rather than fail the batch — the
    connector executor, where one malformed row would otherwise stall the pull
    forever — tests id-derivability with exactly the logic that will run, not a
    reimplementation of it.
    """

    if feed.id_template is not None:
        try:
            return feed.id_template.format(**{k: str(v) for k, v in row.items()})
        except KeyError as exc:
            raise RecordValidationError(
                f"Feed '{feed.name}' id_template references missing field {exc}."
            ) from exc
    raw_id = row.get(feed.id_field)
    if raw_id is None:
        raise RecordValidationError(
            f"Feed '{feed.name}' record is missing id field '{feed.id_field}'."
        )
    return str(raw_id)


__all__ = [
    "coerce_row",
    "derive_record_id",
    "validate_rows",
    "validate_rows_partition",
]
