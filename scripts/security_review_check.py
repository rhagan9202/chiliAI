"""Fail when the security review is overdue or an accepted risk has expired.

Two things rot quietly:

* A quarterly review that nobody schedules. `docs/security_checklist.md` already
  drifted this way — its own header records that the stamp read 2026-05-12 while
  the Findings log carried a dated 2026-07-26 entry.
* An audit-gate exemption that outlives its reasoning. `--ignore-vuln` with a
  code comment is indistinguishable, six months later, from an exemption nobody
  re-read.

This turns both into a build step. Run standalone or via `make check`.

    python scripts/security_review_check.py

`today` is a parameter on every function rather than a clock read, so the tests
do not expire.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import yaml

__all__ = [
    "CheckFailure",
    "ChecklistMeta",
    "check_accepted_risks",
    "check_review_current",
    "main",
    "parse_front_matter",
]

# How long after a review falls due before the build breaks. A review that is a
# fortnight late is a scheduling problem; one that is two months late is a
# process that has stopped.
GRACE_DAYS = 30

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKLIST = _REPO_ROOT / "docs" / "security_checklist.md"
_REGISTER = _REPO_ROOT / ".github" / "security_accepted.yaml"


class CheckFailure(RuntimeError):
    """The inputs could not be read, which is a failure and not a pass."""


def _as_str_keyed_mapping(value: object) -> dict[str, object] | None:
    """Narrow a `yaml.safe_load` result to a string-keyed mapping, or None.

    `safe_load` returns `Any`; narrowing it with `isinstance(x, dict)` yields
    `dict[Unknown, Unknown]`, so iterating `.items()` is a pyright strict error.
    Casting to `dict[object, object]` first pins both halves — the same pattern
    the jsonb decoders use for `json.loads`.
    """

    if not isinstance(value, dict):
        return None
    return {str(k): v for k, v in cast("dict[object, object]", value).items()}


@dataclass(frozen=True)
class ChecklistMeta:
    """Machine-readable header of the security checklist."""

    last_reviewed: date
    cadence_months: int
    owner: str
    prose_dates: tuple[str, ...]

    def next_due(self) -> date:
        """The next review date.

        Month arithmetic without a calendar dependency: adding whole months and
        clamping the day, so a review on the 31st does not skip a short month.
        """

        month_index = self.last_reviewed.month - 1 + self.cadence_months
        year = self.last_reviewed.year + month_index // 12
        month = month_index % 12 + 1
        day = min(self.last_reviewed.day, _days_in_month(year, month))
        return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def parse_front_matter(path: Path) -> ChecklistMeta:
    """Read the YAML front matter from the checklist.

    A missing or unreadable header raises rather than returning a default: a
    checker that passes on input it could not parse is worse than no checker,
    because it reports success.
    """

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise CheckFailure(
            f"{path} has no YAML front matter; expected a '---' block declaring "
            "last_reviewed, cadence_months and owner."
        )
    _, _, rest = text.partition("---\n")
    block, sep, body = rest.partition("\n---")
    if not sep:
        raise CheckFailure(f"{path} has an unterminated front matter block.")

    meta = _as_str_keyed_mapping(yaml.safe_load(block))
    if meta is None:
        raise CheckFailure(f"{path} front matter is not a mapping.")

    last_reviewed = meta.get("last_reviewed")
    if not isinstance(last_reviewed, date):
        raise CheckFailure(
            f"{path} front matter needs `last_reviewed:` as an unquoted YYYY-MM-DD date."
        )
    cadence = meta.get("cadence_months")
    if not isinstance(cadence, int) or cadence <= 0:
        raise CheckFailure(f"{path} front matter needs a positive `cadence_months:`.")
    owner = meta.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        raise CheckFailure(f"{path} front matter needs an `owner:`.")

    return ChecklistMeta(
        last_reviewed=last_reviewed,
        cadence_months=cadence,
        owner=owner,
        prose_dates=_prose_review_dates(body),
    )


def _prose_review_dates(body: str) -> tuple[str, ...]:
    """Every 'Last reviewed: YYYY-MM-DD' written in the human-facing prose."""

    found: list[str] = []
    for line in body.splitlines():
        marker = "Last reviewed:"
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1].strip()
        found.append(tail.split()[0].strip(" ·,"))
    return tuple(found)


def check_review_current(meta: ChecklistMeta, *, today: date) -> list[str]:
    """Problems with review currency; empty means healthy."""

    problems: list[str] = []
    deadline = meta.next_due() + timedelta(days=GRACE_DAYS)
    if today > deadline:
        problems.append(
            f"Security review is overdue: last reviewed {meta.last_reviewed}, "
            f"due {meta.next_due()}, {GRACE_DAYS}-day grace expired {deadline}. "
            f"Owner: {meta.owner}."
        )

    stamp = meta.last_reviewed.isoformat()
    for written in meta.prose_dates:
        if written != stamp:
            problems.append(
                f"Checklist prose says 'Last reviewed: {written}' but front matter "
                f"says {stamp}. These have drifted apart before; keep them equal."
            )
    return problems


def check_accepted_risks(path: Path, *, today: date) -> list[str]:
    """Problems with the accepted-risk register; empty means healthy."""

    register = _as_str_keyed_mapping(yaml.safe_load(path.read_text(encoding="utf-8")))
    if register is None:
        raise CheckFailure(f"{path} is not a mapping of ecosystem -> entries.")

    problems: list[str] = []
    for ecosystem, raw_entries in register.items():
        if raw_entries is None:
            continue
        if not isinstance(raw_entries, list):
            problems.append(f"{ecosystem}: expected a list of acceptances.")
            continue
        for raw in cast(list[object], raw_entries):
            entry = _as_str_keyed_mapping(raw)
            if entry is None:
                problems.append(f"{ecosystem}: acceptance entries must be mappings.")
                continue
            advisory = entry.get("id")
            label = f"{ecosystem}:{advisory if isinstance(advisory, str) else '<no id>'}"

            if not isinstance(advisory, str) or not advisory.strip():
                problems.append(f"{label}: acceptance needs an advisory `id`.")
            rationale = entry.get("rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                problems.append(
                    f"{label}: acceptance needs a `rationale` saying why this "
                    "codebase is unaffected."
                )
            review_by = entry.get("review_by")
            if not isinstance(review_by, date):
                problems.append(
                    f"{label}: acceptance needs `review_by` as an unquoted "
                    "YYYY-MM-DD date. An acceptance without an expiry is a mute."
                )
            elif today > review_by:
                problems.append(
                    f"{label}: acceptance expired {review_by} — re-read the "
                    "advisory and either renew with fresh reasoning or drop it."
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checklist", nargs="?", type=Path, default=_CHECKLIST)
    parser.add_argument("--register", type=Path, default=_REGISTER)
    args = parser.parse_args(argv)

    checklist_path: Path = args.checklist
    register_path: Path = args.register
    today = date.today()

    try:
        problems = check_review_current(parse_front_matter(checklist_path), today=today)
        problems += check_accepted_risks(register_path, today=today)
    except CheckFailure as exc:
        print(f"security-review-check: {exc}", file=sys.stderr)
        return 2

    for problem in problems:
        print(f"security-review-check: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("security-review-check: review current, accepted risks all live.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
