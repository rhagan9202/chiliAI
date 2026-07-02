"""Tests for type-aware property normalization (ingestion.14)."""

from __future__ import annotations

from ingestion.normalization import normalize_properties
from shared.types import EntityDefinition, PropertyDefinition, PropertyType


def _definition(**props: PropertyDefinition) -> EntityDefinition:
    return EntityDefinition(
        name="claim",
        display_label="Claim",
        icon="file",
        properties=dict(props),
    )


def _decimal_def() -> EntityDefinition:
    return _definition(amount=PropertyDefinition(type=PropertyType.DECIMAL, display="Amount"))


class TestDecimalNormalization:
    def test_period_decimal_string_becomes_float(self) -> None:
        normalized, errors = normalize_properties({"amount": "412.00"}, _decimal_def())
        assert errors == []
        assert normalized["amount"] == 412.0
        assert isinstance(normalized["amount"], float)

    def test_comma_decimal_separator_becomes_float(self) -> None:
        normalized, errors = normalize_properties({"amount": "412,50"}, _decimal_def())
        assert errors == []
        assert normalized["amount"] == 412.5

    def test_existing_float_passes_through(self) -> None:
        normalized, errors = normalize_properties({"amount": 99.9}, _decimal_def())
        assert errors == []
        assert normalized["amount"] == 99.9

    def test_existing_int_passes_through(self) -> None:
        normalized, errors = normalize_properties({"amount": 7}, _decimal_def())
        assert errors == []
        assert normalized["amount"] == 7

    def test_unparseable_string_reports_normalization_failure(self) -> None:
        normalized, errors = normalize_properties({"amount": "four hundred"}, _decimal_def())
        assert len(errors) == 1
        assert "normalization_failed" in errors[0]
        assert "amount" in errors[0]
        # Original value retained so validate_entity reports the type mismatch too.
        assert normalized["amount"] == "four hundred"

    def test_boolean_is_not_treated_as_number(self) -> None:
        normalized, errors = normalize_properties({"amount": True}, _decimal_def())
        assert len(errors) == 1
        assert "normalization_failed" in errors[0]
        assert normalized["amount"] is True


class TestIntegerNormalization:
    def _def(self) -> EntityDefinition:
        return _definition(count=PropertyDefinition(type=PropertyType.INTEGER, display="Count"))

    def test_integer_string_becomes_int(self) -> None:
        normalized, errors = normalize_properties({"count": "42"}, self._def())
        assert errors == []
        assert normalized["count"] == 42
        assert isinstance(normalized["count"], int)

    def test_existing_int_passes_through(self) -> None:
        normalized, errors = normalize_properties({"count": 5}, self._def())
        assert errors == []
        assert normalized["count"] == 5

    def test_non_integer_string_fails(self) -> None:
        _, errors = normalize_properties({"count": "4.5"}, self._def())
        assert len(errors) == 1
        assert "normalization_failed" in errors[0]


class TestBooleanNormalization:
    def _def(self) -> EntityDefinition:
        return _definition(active=PropertyDefinition(type=PropertyType.BOOLEAN, display="Active"))

    def test_truthy_strings_become_true(self) -> None:
        for raw in ("true", "True", "YES", "1"):
            normalized, errors = normalize_properties({"active": raw}, self._def())
            assert errors == []
            assert normalized["active"] is True

    def test_falsy_strings_become_false(self) -> None:
        for raw in ("false", "no", "0", "No"):
            normalized, errors = normalize_properties({"active": raw}, self._def())
            assert errors == []
            assert normalized["active"] is False

    def test_existing_bool_passes_through(self) -> None:
        normalized, errors = normalize_properties({"active": True}, self._def())
        assert errors == []
        assert normalized["active"] is True

    def test_unrecognized_string_fails(self) -> None:
        _, errors = normalize_properties({"active": "maybe"}, self._def())
        assert len(errors) == 1
        assert "normalization_failed" in errors[0]


class TestDateNormalization:
    def _def(self) -> EntityDefinition:
        return _definition(billed=PropertyDefinition(type=PropertyType.DATE, display="Billed"))

    def test_iso_date_passes_through(self) -> None:
        normalized, errors = normalize_properties({"billed": "2026-05-14"}, self._def())
        assert errors == []
        assert normalized["billed"] == "2026-05-14"

    def test_us_slash_date_becomes_iso(self) -> None:
        normalized, errors = normalize_properties({"billed": "05/14/2026"}, self._def())
        assert errors == []
        assert normalized["billed"] == "2026-05-14"

    def test_dotted_european_date_becomes_iso(self) -> None:
        normalized, errors = normalize_properties({"billed": "14.05.2026"}, self._def())
        assert errors == []
        assert normalized["billed"] == "2026-05-14"

    def test_unparseable_date_fails(self) -> None:
        _, errors = normalize_properties({"billed": "next Tuesday"}, self._def())
        assert len(errors) == 1
        assert "normalization_failed" in errors[0]


class TestEnumNormalization:
    def _def(self) -> EntityDefinition:
        return _definition(
            status=PropertyDefinition(
                type=PropertyType.ENUM,
                display="Status",
                enum_values=["Paid", "Denied"],
            )
        )

    def test_case_insensitive_match_becomes_canonical(self) -> None:
        normalized, errors = normalize_properties({"status": "paid"}, self._def())
        assert errors == []
        assert normalized["status"] == "Paid"

    def test_exact_match_passes_through(self) -> None:
        normalized, errors = normalize_properties({"status": "Denied"}, self._def())
        assert errors == []
        assert normalized["status"] == "Denied"

    def test_unknown_value_left_for_schema_validation(self) -> None:
        # Not a normalization failure: validate_entity owns enum-membership errors.
        normalized, errors = normalize_properties({"status": "pending"}, self._def())
        assert errors == []
        assert normalized["status"] == "pending"


class TestStringAndPassthrough:
    def test_string_values_are_stripped(self) -> None:
        definition = _definition(
            name=PropertyDefinition(type=PropertyType.STRING, display="Name")
        )
        normalized, errors = normalize_properties({"name": "  Alice  "}, definition)
        assert errors == []
        assert normalized["name"] == "Alice"

    def test_unknown_property_passes_through_untouched(self) -> None:
        normalized, errors = normalize_properties({"mystery": " x "}, _decimal_def())
        assert errors == []
        assert normalized["mystery"] == " x "

    def test_list_and_nested_pass_through(self) -> None:
        definition = _definition(
            tags=PropertyDefinition(type=PropertyType.LIST, display="Tags"),
            extra=PropertyDefinition(type=PropertyType.NESTED, display="Extra"),
        )
        normalized, errors = normalize_properties(
            {"tags": ["a", "b"], "extra": {"k": "v"}}, definition
        )
        assert errors == []
        assert normalized["tags"] == ["a", "b"]
        assert normalized["extra"] == {"k": "v"}
