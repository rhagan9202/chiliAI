"""Tests for shared utility helpers."""

from __future__ import annotations

from datetime import timezone
from uuid import UUID

from shared.utils import generate_id, normalize_text, utc_now


def test_generate_id_returns_uuid4_string() -> None:
    generated_id = generate_id()

    assert UUID(generated_id).version == 4


def test_generate_id_returns_unique_values() -> None:
    first_id = generate_id()
    second_id = generate_id()

    assert first_id != second_id


def test_normalize_text_collapses_whitespace_and_lowercases() -> None:
    assert normalize_text("  Hello\n\tWorld  ") == "hello world"


def test_utcnow_returns_timezone_aware_utc_datetime() -> None:
    timestamp = utc_now()

    assert timestamp.tzinfo is timezone.utc