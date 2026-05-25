"""Tests for scripts/backlog_consistency.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.backlog_consistency import (
    Story,
    detect_cycles,
    parse_all,
    parse_file,
    validate_prereq_references,
    validate_status_invariants,
    warn_xl_size,
)

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


def test_parse_all_loads_directory(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    (tmp_path / "b.md").write_text("# empty\n")  # no stories
    stories = parse_all(tmp_path)
    assert set(stories.keys()) == {"foo.01", "foo.02"}


def test_parse_all_duplicate_id_raises(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    (tmp_path / "b.md").write_text((FIXTURES / "simple.md").read_text())
    with pytest.raises(ValueError, match="Duplicate ID foo.01"):
        parse_all(tmp_path)


def test_parse_all_skips_readme(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    # README.md must not be parsed as a backlog file even if it has "## Story" lines.
    (tmp_path / "README.md").write_text("## Story foo.99: Should not be parsed\n")
    stories = parse_all(tmp_path)
    assert "foo.99" not in stories


def test_validate_prereq_references_passes(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    stories = parse_all(tmp_path)
    errors = validate_prereq_references(stories)
    assert errors == []


def test_validate_prereq_references_unresolved(tmp_path: Path) -> None:
    bad = (FIXTURES / "simple.md").read_text().replace("[foo.01]", "[foo.99]")
    (tmp_path / "a.md").write_text(bad)
    stories = parse_all(tmp_path)
    errors = validate_prereq_references(stories)
    assert len(errors) == 1
    assert "foo.02" in errors[0] and "foo.99" in errors[0]


def test_detect_cycles_finds_pair(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "cycle.md").read_text())
    stories = parse_all(tmp_path)
    cycles = detect_cycles(stories)
    assert len(cycles) >= 1
    assert set(cycles[0]) == {"foo.01", "foo.02"}


def test_detect_cycles_clean(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    stories = parse_all(tmp_path)
    assert detect_cycles(stories) == []


def test_status_done_must_have_done_line(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "done_missing_done_line.md").read_text())
    errors = validate_status_invariants(parse_all(tmp_path))
    assert any("Done line" in e for e in errors)


def test_status_done_must_have_all_ac_checked(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "done_unchecked_ac.md").read_text())
    errors = validate_status_invariants(parse_all(tmp_path))
    assert any("unchecked acceptance criteria" in e for e in errors)


def test_status_in_progress_needs_done_prereqs(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(
        (FIXTURES / "in_progress_with_planned_prereq.md").read_text()
    )
    errors = validate_status_invariants(parse_all(tmp_path))
    assert any("not all prerequisites are done" in e for e in errors)


def test_status_invariants_clean(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    errors = validate_status_invariants(parse_all(tmp_path))
    assert errors == []


def test_warn_xl_size_returns_warnings(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "xl_story.md").read_text())
    stories = parse_all(tmp_path)
    warnings = warn_xl_size(stories)
    assert len(warnings) == 1
    assert "XL" in warnings[0]


def test_warn_xl_size_clean(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    assert warn_xl_size(parse_all(tmp_path)) == []
