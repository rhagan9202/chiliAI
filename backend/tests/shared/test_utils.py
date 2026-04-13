"""Tests for shared utility helpers."""

from __future__ import annotations

from uuid import UUID

from shared.utils import generate_id, normalize_text


def test_generate_id_returns_uuid4_string() -> None:
    generated_id = generate_id()

    assert UUID(generated_id).version == 4


def test_generate_id_returns_unique_values() -> None:
    first_id = generate_id()
    second_id = generate_id()

    assert first_id != second_id


def test_normalize_text_collapses_whitespace_and_lowercases() -> None:
    assert normalize_text("  Hello\n\tWorld  ") == "hello world"