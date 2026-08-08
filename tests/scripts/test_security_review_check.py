"""Tests for the security review / accepted-risk staleness checker.

`today` is injected everywhere rather than read from the clock, so these do not
start failing on a date boundary — a test that only passes until October is a
worse liability than the drift it guards.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.security_review_check import (  # noqa: E402
    CheckFailure,
    main,
    check_accepted_risks,
    check_review_current,
    parse_front_matter,
)

_CHECKLIST = """---
last_reviewed: 2026-07-26
cadence_months: 3
owner: Platform Security
---

# chiliAI Security Audit Checklist

> Owner: Platform Security · Last reviewed: 2026-07-26 · Cadence: **quarterly**
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "security_checklist.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestFrontMatter:
    def test_it_reads_the_review_date(self, tmp_path: Path) -> None:
        meta = parse_front_matter(_write(tmp_path, _CHECKLIST))

        assert meta.last_reviewed == date(2026, 7, 26)
        assert meta.cadence_months == 3

    def test_a_file_without_front_matter_is_an_error_not_a_pass(
        self, tmp_path: Path
    ) -> None:
        """Silently passing an unparseable file is how a checker becomes decorative."""
        path = _write(tmp_path, "# chiliAI Security Audit Checklist\n")

        with pytest.raises(CheckFailure, match="front matter"):
            parse_front_matter(path)


class TestReviewCurrency:
    def test_a_review_inside_the_cadence_passes(self, tmp_path: Path) -> None:
        meta = parse_front_matter(_write(tmp_path, _CHECKLIST))

        assert check_review_current(meta, today=date(2026, 9, 1)) == []

    def test_the_grace_window_is_inclusive_at_its_edge(self, tmp_path: Path) -> None:
        """Due 2026-10-26 plus 30 days of grace: the 30th day is still fine."""
        meta = parse_front_matter(_write(tmp_path, _CHECKLIST))

        assert check_review_current(meta, today=date(2026, 11, 25)) == []

    def test_one_day_past_the_grace_window_fails(self, tmp_path: Path) -> None:
        meta = parse_front_matter(_write(tmp_path, _CHECKLIST))

        problems = check_review_current(meta, today=date(2026, 11, 26))

        assert len(problems) == 1
        assert "overdue" in problems[0]

    def test_the_prose_line_must_agree_with_the_front_matter(
        self, tmp_path: Path
    ) -> None:
        """This file has already drifted this exact way once.

        Its own header records that the stamp read 2026-05-12 while the Findings
        log carried a dated 2026-07-26 entry. Two copies of one date will drift
        again unless something compares them.
        """
        path = _write(tmp_path, _CHECKLIST.replace("Last reviewed: 2026-07-26", "Last reviewed: 2026-05-12"))
        meta = parse_front_matter(path)

        problems = check_review_current(meta, today=date(2026, 9, 1))

        assert len(problems) == 1
        assert "2026-05-12" in problems[0]


class TestAcceptedRisks:
    def _register(self, tmp_path: Path, review_by: str) -> Path:
        path = tmp_path / "security_accepted.yaml"
        path.write_text(
            "pip:\n"
            "  - id: PYSEC-2026-1325\n"
            "    package: ecdsa\n"
            "    rationale: RS256 pinned, ECDSA path unreachable.\n"
            "    accepted_on: 2026-07-12\n"
            f"    review_by: {review_by}\n"
            "    owner: Platform Security\n"
            "npm: []\n",
            encoding="utf-8",
        )
        return path

    def test_a_live_acceptance_passes(self, tmp_path: Path) -> None:
        path = self._register(tmp_path, "2026-10-26")

        assert check_accepted_risks(path, today=date(2026, 8, 8)) == []

    def test_an_expired_acceptance_fails(self, tmp_path: Path) -> None:
        """An acceptance is a decision with an expiry, not a permanent mute."""
        path = self._register(tmp_path, "2026-08-01")

        problems = check_accepted_risks(path, today=date(2026, 8, 8))

        assert len(problems) == 1
        assert "PYSEC-2026-1325" in problems[0]

    def test_an_acceptance_without_a_rationale_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "security_accepted.yaml"
        path.write_text(
            "pip:\n  - id: PYSEC-9999-0001\n    package: x\n    review_by: 2027-01-01\n",
            encoding="utf-8",
        )

        problems = check_accepted_risks(path, today=date(2026, 8, 8))

        assert any("rationale" in p for p in problems)

    def test_an_acceptance_without_a_review_date_fails(self, tmp_path: Path) -> None:
        """No expiry is the failure mode this register exists to prevent."""
        path = tmp_path / "security_accepted.yaml"
        path.write_text(
            "pip:\n  - id: PYSEC-9999-0002\n    package: x\n    rationale: because\n",
            encoding="utf-8",
        )

        problems = check_accepted_risks(path, today=date(2026, 8, 8))

        assert any("review_by" in p for p in problems)

    def test_an_empty_register_passes(self, tmp_path: Path) -> None:
        path = tmp_path / "security_accepted.yaml"
        path.write_text("pip: []\nnpm: []\n", encoding="utf-8")

        assert check_accepted_risks(path, today=date(2026, 8, 8)) == []


class TestRepositoryFilesAreValid:
    """The checked-in files must satisfy the checker they ship with."""

    def test_the_real_checklist_parses(self) -> None:
        root = Path(__file__).resolve().parents[2]
        meta = parse_front_matter(root / "docs" / "security_checklist.md")

        assert meta.cadence_months > 0

    def test_the_real_register_has_no_undated_acceptances(self) -> None:
        root = Path(__file__).resolve().parents[2]
        problems = [
            p
            for p in check_accepted_risks(
                root / ".github" / "security_accepted.yaml", today=date(2026, 8, 8)
            )
            if "review_by" in p or "rationale" in p
        ]

        assert problems == []


class TestMalformedInputsFailLoudly:
    """Every unreadable-input path must raise, never return a clean result."""

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("---\nlast_reviewed: 2026-07-26\ncadence_months: 3\n", "unterminated"),
            ("---\n- not-a-mapping\n---\n", "not a mapping"),
            ("---\ncadence_months: 3\nowner: X\n---\n", "last_reviewed"),
            ("---\nlast_reviewed: 2026-07-26\nowner: X\n---\n", "cadence_months"),
            (
                "---\nlast_reviewed: 2026-07-26\ncadence_months: 0\nowner: X\n---\n",
                "cadence_months",
            ),
            ("---\nlast_reviewed: 2026-07-26\ncadence_months: 3\n---\n", "owner"),
            (
                '---\nlast_reviewed: "2026-07-26"\ncadence_months: 3\nowner: X\n---\n',
                "last_reviewed",
            ),
        ],
    )
    def test_bad_front_matter_raises(
        self, tmp_path: Path, body: str, expected: str
    ) -> None:
        with pytest.raises(CheckFailure, match=expected):
            parse_front_matter(_write(tmp_path, body))

    def test_a_register_that_is_not_a_mapping_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "security_accepted.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")

        with pytest.raises(CheckFailure, match="mapping"):
            check_accepted_risks(path, today=date(2026, 8, 8))

    def test_a_non_list_ecosystem_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "security_accepted.yaml"
        path.write_text("pip: not-a-list\n", encoding="utf-8")

        assert any("list" in p for p in check_accepted_risks(path, today=date(2026, 8, 8)))

    def test_a_non_mapping_entry_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "security_accepted.yaml"
        path.write_text("pip:\n  - just-a-string\n", encoding="utf-8")

        assert any("mappings" in p for p in check_accepted_risks(path, today=date(2026, 8, 8)))

    def test_an_entry_without_an_id_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "security_accepted.yaml"
        path.write_text(
            "pip:\n  - package: x\n    rationale: y\n    review_by: 2027-01-01\n",
            encoding="utf-8",
        )

        assert any("`id`" in p for p in check_accepted_risks(path, today=date(2026, 8, 8)))

    def test_a_null_ecosystem_is_not_an_error(self, tmp_path: Path) -> None:
        """`npm:` with nothing under it is an empty register, not a broken one."""
        path = tmp_path / "security_accepted.yaml"
        path.write_text("pip: []\nnpm:\n", encoding="utf-8")

        assert check_accepted_risks(path, today=date(2026, 8, 8)) == []


class TestNextDue:
    def test_it_adds_the_cadence_in_months(self, tmp_path: Path) -> None:
        meta = parse_front_matter(_write(tmp_path, _CHECKLIST))

        assert meta.next_due() == date(2026, 10, 26)

    def test_it_rolls_over_the_year(self, tmp_path: Path) -> None:
        meta = parse_front_matter(
            _write(tmp_path, _CHECKLIST.replace("2026-07-26", "2026-11-26"))
        )

        assert meta.next_due() == date(2027, 2, 26)

    def test_it_clamps_a_day_that_the_target_month_lacks(self, tmp_path: Path) -> None:
        """31 Dec + 2 months is 28 Feb, not a crash and not 3 March."""
        meta = parse_front_matter(
            _write(
                tmp_path,
                _CHECKLIST.replace("2026-07-26", "2026-12-31").replace(
                    "cadence_months: 3", "cadence_months: 2"
                ),
            )
        )

        assert meta.next_due() == date(2027, 2, 28)

    def test_december_cadence_does_not_overflow_the_month_lookup(
        self, tmp_path: Path
    ) -> None:
        meta = parse_front_matter(
            _write(
                tmp_path,
                _CHECKLIST.replace("2026-07-26", "2026-09-30").replace(
                    "cadence_months: 3", "cadence_months: 3"
                ),
            )
        )

        assert meta.next_due() == date(2026, 12, 30)


class TestCli:
    def _files(self, tmp_path: Path, *, review_by: str) -> tuple[Path, Path]:
        checklist = _write(tmp_path, _CHECKLIST)
        register = tmp_path / "security_accepted.yaml"
        register.write_text(
            "pip:\n"
            "  - id: PYSEC-2026-1325\n"
            "    package: ecdsa\n"
            "    rationale: RS256 pinned.\n"
            f"    review_by: {review_by}\n",
            encoding="utf-8",
        )
        return checklist, register

    def test_it_exits_zero_when_everything_is_current(self, tmp_path: Path) -> None:
        checklist, register = self._files(tmp_path, review_by="2099-01-01")

        assert main([str(checklist), "--register", str(register)]) == 0

    def test_it_exits_one_on_a_real_problem(self, tmp_path: Path) -> None:
        checklist, register = self._files(tmp_path, review_by="2000-01-01")

        assert main([str(checklist), "--register", str(register)]) == 1

    def test_it_exits_two_when_the_input_cannot_be_read(self, tmp_path: Path) -> None:
        """Unreadable input is distinct from a failed check, and louder."""
        # Order matters: `_files` writes the checklist too, so the malformed
        # content has to land after it or it is silently overwritten and the
        # test passes for the wrong reason.
        checklist, register = self._files(tmp_path, review_by="2099-01-01")
        checklist.write_text("# no front matter\n", encoding="utf-8")

        assert main([str(checklist), "--register", str(register)]) == 2
