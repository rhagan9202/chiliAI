"""Unit tests for input validation helpers (E10-S10)."""

from __future__ import annotations

import pytest

from shared.validation import (
    WINDOWS_RESERVED_NAMES,
    sanitize_filename,
    validate_content_type,
    validate_query_length,
)


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "raw,expected_substring",
        [
            ("../../etc/passwd", "passwd"),
            ("..\\..\\boot.ini", "boot.ini"),
            ("/absolute/path/file.txt", "file.txt"),
            ("normal-name.csv", "normal-name.csv"),
        ],
    )
    def test_strips_path_components(self, raw: str, expected_substring: str) -> None:
        cleaned = sanitize_filename(raw)
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert ".." not in cleaned
        assert expected_substring.replace("/", "").replace("\\", "") in cleaned

    def test_strips_null_byte(self) -> None:
        cleaned = sanitize_filename("evil\x00.exe")
        assert "\x00" not in cleaned

    def test_strips_control_chars(self) -> None:
        cleaned = sanitize_filename("name\x01\x02.txt")
        assert "\x01" not in cleaned
        assert "\x02" not in cleaned

    def test_empty_input_returns_default(self) -> None:
        assert sanitize_filename("") == "upload"
        assert sanitize_filename("....") == "upload"
        assert sanitize_filename("///") == "upload"

    def test_windows_reserved_name_is_prefixed(self) -> None:
        cleaned = sanitize_filename("CON")
        assert cleaned.startswith("_")
        # All members of WINDOWS_RESERVED_NAMES collapse to '_NAME'
        assert any(reserved in cleaned for reserved in WINDOWS_RESERVED_NAMES)

    def test_non_string_input_returns_default(self) -> None:
        # The implementation guards against non-string input via isinstance.
        assert sanitize_filename(cast_object_as_str(None)) == "upload"


def cast_object_as_str(value: object) -> str:
    # Helper for the deliberately-typed bad input case above.
    return value  # type: ignore[return-value]


class TestValidateContentType:
    def test_exact_match(self) -> None:
        assert validate_content_type("text/plain", {"text/plain"})

    def test_match_strips_parameters(self) -> None:
        assert validate_content_type(
            "application/json; charset=utf-8", {"application/json"}
        )

    def test_case_insensitive(self) -> None:
        assert validate_content_type("Application/JSON", {"application/json"})

    def test_none_rejected(self) -> None:
        assert not validate_content_type(None, {"text/plain"})

    def test_unknown_rejected(self) -> None:
        assert not validate_content_type(
            "application/octet-stream", {"text/plain", "application/json"}
        )


class TestValidateQueryLength:
    def test_returns_trimmed_value(self) -> None:
        assert validate_query_length("  hello  ", 100) == "hello"

    def test_overflow_raises(self) -> None:
        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_query_length("a" * 50, 10)

    def test_at_limit_succeeds(self) -> None:
        # Exactly at the limit should pass.
        cleaned = validate_query_length("x" * 10, 10)
        assert cleaned == "x" * 10

    def test_empty_string_passes(self) -> None:
        assert validate_query_length("", 100) == ""

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_query_length(cast_object_as_str(42), 100)
