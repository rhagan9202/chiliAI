"""Tests for scripts/backlog_consistency.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.backlog_consistency import (
    Story,
    compute_critical_path,
    compute_ready_set,
    compute_unblocks,
    detect_cycles,
    parse_all,
    parse_file,
    rewrite_readme,
    rewrite_unblocks,
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


def test_compute_unblocks_inverts(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    stories = parse_all(tmp_path)
    result = compute_unblocks(stories)
    assert result["foo.01"] == ["foo.02"]
    assert result["foo.02"] == []


def test_rewrite_unblocks_updates_file(tmp_path: Path) -> None:
    src = (FIXTURES / "simple.md").read_text()
    target = tmp_path / "a.md"
    target.write_text(src)
    stories = parse_all(tmp_path)
    computed = compute_unblocks(stories)
    changes = rewrite_unblocks(stories, computed, check_only=False)
    assert len(changes) == 1
    new_text = target.read_text()
    assert "**Unblocks:** [foo.02]" in new_text


def test_rewrite_unblocks_check_only_reports_no_write(tmp_path: Path) -> None:
    src = (FIXTURES / "simple.md").read_text()
    target = tmp_path / "a.md"
    target.write_text(src)
    stories = parse_all(tmp_path)
    computed = compute_unblocks(stories)
    changes = rewrite_unblocks(stories, computed, check_only=True)
    assert len(changes) == 1
    assert target.read_text() == src


def test_ready_set(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    stories = parse_all(tmp_path)
    ready = compute_ready_set(stories)
    # foo.01 is planned with no prereqs -> ready. foo.02 is done -> not in ready.
    assert [s.id for s in ready] == ["foo.01"]


def test_critical_path(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    stories = parse_all(tmp_path)
    path = compute_critical_path(stories)
    # foo.01 (S=1) -> foo.02 (M=2) — total 3
    assert [s.id for s in path] == ["foo.01", "foo.02"]


def test_critical_path_empty_on_cycle(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "cycle.md").read_text())
    stories = parse_all(tmp_path)
    assert compute_critical_path(stories) == []


def test_rewrite_readme_replaces_marker_sections(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    readme = tmp_path / "README.md"
    readme.write_text(
        "# X\n\n"
        "<!-- BEGIN: status-rollup -->\nOLD\n<!-- END: status-rollup -->\n\n"
        "<!-- BEGIN: ready-set -->\nOLD\n<!-- END: ready-set -->\n\n"
        "<!-- BEGIN: critical-path -->\nOLD\n<!-- END: critical-path -->\n"
    )
    stories = parse_all(tmp_path)
    changes = rewrite_readme(readme, stories, check_only=False)
    assert len(changes) == 3
    new_text = readme.read_text()
    assert "OLD" not in new_text
    assert "foo.01" in new_text  # ready set rendered


def test_rewrite_readme_check_only_does_not_write(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    readme = tmp_path / "README.md"
    initial = (
        "<!-- BEGIN: status-rollup -->\nOLD\n<!-- END: status-rollup -->\n"
        "<!-- BEGIN: ready-set -->\nOLD\n<!-- END: ready-set -->\n"
        "<!-- BEGIN: critical-path -->\nOLD\n<!-- END: critical-path -->\n"
    )
    readme.write_text(initial)
    stories = parse_all(tmp_path)
    changes = rewrite_readme(readme, stories, check_only=True)
    assert len(changes) == 3
    assert readme.read_text() == initial


def test_rewrite_readme_missing_marker_raises(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text((FIXTURES / "simple.md").read_text())
    readme = tmp_path / "README.md"
    readme.write_text("# no markers here\n")
    stories = parse_all(tmp_path)
    with pytest.raises(RuntimeError, match="status-rollup"):
        rewrite_readme(readme, stories, check_only=True)


def test_rewrite_unblocks_no_change_when_correct(tmp_path: Path) -> None:
    # Pre-populate the Unblocks line correctly and verify zero changes reported.
    src = (FIXTURES / "simple.md").read_text().replace(
        "**Unblocks:** []\n**Estimated size:** S",
        "**Unblocks:** [foo.02]\n**Estimated size:** S",
        1,
    )
    target = tmp_path / "a.md"
    target.write_text(src)
    stories = parse_all(tmp_path)
    computed = compute_unblocks(stories)
    changes = rewrite_unblocks(stories, computed, check_only=False)
    assert changes == []
