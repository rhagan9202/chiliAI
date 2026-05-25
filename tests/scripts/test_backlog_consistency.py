"""Tests for scripts/backlog_consistency.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.backlog_consistency import Story, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_simple() -> None:
    stories = parse_file(FIXTURES / "simple.md")
    assert len(stories) == 2
    first = stories[0]
    assert first.id == "foo.01"
    assert first.status == "planned"
    assert first.prerequisites == []
    assert first.unblocks == []
    assert first.estimated_size == "S"
    assert first.spec == []
    assert first.done_line is None
    assert first.acceptance_total == 2
    assert first.acceptance_checked == 0
    second = stories[1]
    assert second.id == "foo.02"
    assert second.status == "done"
    assert second.prerequisites == ["foo.01"]
    assert second.done_line == "2026-05-24 · abc1234 · #42"
    assert second.acceptance_total == 2
    assert second.acceptance_checked == 2
    # Story dataclass sanity
    assert isinstance(first, Story)


def test_parse_file_missing_field_raises() -> None:
    with pytest.raises(KeyError, match="Status"):
        parse_file(FIXTURES / "missing_field.md")


def test_parse_file_bad_id_raises() -> None:
    with pytest.raises(ValueError, match="ID"):
        parse_file(FIXTURES / "bad_id.md")
