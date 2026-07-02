"""Type-aware property normalization applied before schema validation.

Extractors (LLM and pattern based) and structured-record mappers emit raw
property values — frequently strings — while ``shared.types.validate_entity``
enforces typed values against ``PropertyDefinition.type``. This module
converts common raw representations (string decimals, regionally formatted
dates, yes/no booleans, differently cased enum values) into the platform's
canonical value types so validly extracted entities are not rejected as
schema mismatches (backlog story ingestion.14).

Decimals normalize to ``float`` — the platform's canonical decimal
representation (``shared.types._matches_property_type`` accepts int/float,
range checks coerce via ``float``, and artifacts round-trip through JSON).
A typed-``Decimal`` migration is a separate story. ``list`` per-element
normalization is not possible because ``PropertyDefinition`` declares no
element type; list and nested values pass through untouched.
"""

from __future__ import annotations

from datetime import date, datetime

from shared.types import EntityDefinition, PropertyDefinition, PropertyType

__all__ = ["normalize_properties"]


_TRUTHY = {"true", "yes", "1"}
_FALSY = {"false", "no", "0"}

# Non-ISO formats accepted for DATE properties, tried in order. ISO 8601 is
# handled by date.fromisoformat first and always wins.
_DATE_FORMATS = ("%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y")


class _NormalizationFailure(Exception):
    """Raised internally when a raw value cannot be converted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def normalize_properties(
    properties: dict[str, object],
    definition: EntityDefinition,
) -> tuple[dict[str, object], list[str]]:
    """Normalize ``properties`` against ``definition``'s property types.

    Returns a normalized copy plus a list of error strings (prefixed
    ``normalization_failed``) for values that could not be converted.
    Failed values are retained unmodified so downstream schema validation
    still reports the type mismatch on the original value. Properties not
    declared on the definition pass through untouched — unexpected-property
    handling belongs to the validator.
    """

    normalized: dict[str, object] = {}
    errors: list[str] = []
    for name, value in properties.items():
        property_definition = definition.properties.get(name)
        if property_definition is None:
            normalized[name] = value
            continue
        try:
            normalized[name] = _normalize_value(value, property_definition)
        except _NormalizationFailure as failure:
            normalized[name] = value
            errors.append(
                f"normalization_failed: property '{name}' on entity type "
                f"'{definition.name}': {failure.reason}"
            )
    return normalized, errors


def _normalize_value(value: object, definition: PropertyDefinition) -> object:
    property_type = definition.type
    if property_type is PropertyType.STRING:
        return value.strip() if isinstance(value, str) else value
    if property_type is PropertyType.DECIMAL:
        return _normalize_decimal(value)
    if property_type is PropertyType.INTEGER:
        return _normalize_integer(value)
    if property_type is PropertyType.BOOLEAN:
        return _normalize_boolean(value)
    if property_type is PropertyType.DATE:
        return _normalize_date(value)
    if property_type is PropertyType.ENUM:
        return _normalize_enum(value, definition)
    # LIST and NESTED pass through: no element type exists in the schema.
    return value


def _normalize_decimal(value: object) -> object:
    if isinstance(value, bool):
        raise _NormalizationFailure(f"boolean {value!r} is not a decimal")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if "," in candidate and "." not in candidate:
            candidate = candidate.replace(",", ".")
        try:
            return float(candidate)
        except ValueError:
            raise _NormalizationFailure(
                f"could not parse {value!r} as a decimal"
            ) from None
    raise _NormalizationFailure(f"unsupported decimal value {value!r}")


def _normalize_integer(value: object) -> object:
    if isinstance(value, bool):
        raise _NormalizationFailure(f"boolean {value!r} is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise _NormalizationFailure(
                f"could not parse {value!r} as an integer"
            ) from None
    raise _NormalizationFailure(f"unsupported integer value {value!r}")


def _normalize_boolean(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSY:
            return False
        raise _NormalizationFailure(f"could not parse {value!r} as a boolean")
    raise _NormalizationFailure(f"unsupported boolean value {value!r}")


def _normalize_date(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            pass
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue
        raise _NormalizationFailure(f"could not parse {value!r} as a date")
    raise _NormalizationFailure(f"unsupported date value {value!r}")


def _normalize_enum(value: object, definition: PropertyDefinition) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    for allowed in definition.enum_values or []:
        if stripped.lower() == allowed.lower():
            return allowed
    # Unknown values are a schema concern (enum membership), not normalization.
    return stripped
