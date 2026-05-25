"""chiliAI backlog consistency pass.

Parses the rich-format backlog stories under ``docs/backlog/``, validates
DAG/status invariants, computes Unblocks/ready-set/critical-path, and
rewrites the auto-generated marker sections in ``docs/backlog/README.md``.

Run as a script:

    python scripts/backlog_consistency.py [--backlog-dir DIR] [--check] [--strict]

Python 3.12 standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


STORY_HEADING = re.compile(r"^## Story (\S+):", re.MULTILINE)
FIELD = re.compile(r"^\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.*?)\s*$", re.MULTILINE)
AC_BOX = re.compile(r"^- \[(?P<mark>[ xX])\]", re.MULTILINE)
ID_LIST = re.compile(r"\[(?P<inner>[^\]]*)\]")


@dataclass
class Story:
    """A single backlog story parsed from a rich-format markdown file."""

    id: str
    file: Path
    status: str  # planned | in-progress | done | dropped
    prerequisites: list[str]
    unblocks: list[str]
    estimated_size: str  # S | M | L | XL
    spec: list[str]
    done_line: str | None
    acceptance_total: int
    acceptance_checked: int


def _parse_id_list(raw: str) -> list[str]:
    """Parse ``[a.01, b.02]``-style ID lists. Empty ``[]`` → ``[]``."""
    m = ID_LIST.search(raw)
    if not m:
        return []
    inner = m.group("inner").strip()
    if not inner:
        return []
    return [x.strip() for x in inner.split(",")]


def parse_file(path: Path) -> list[Story]:
    """Parse every ``## Story <id>:`` block in ``path`` into a list of Story."""
    text = path.read_text(encoding="utf-8")
    headings = list(STORY_HEADING.finditer(text))
    stories: list[Story] = []
    for i, heading in enumerate(headings):
        start = heading.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end]
        fields: dict[str, str] = {}
        for fmatch in FIELD.finditer(body):
            fields[fmatch.group("key").strip()] = fmatch.group("value").strip()

        ac_section_start = body.find("### Acceptance Criteria")
        if ac_section_start == -1:
            ac_total = 0
            ac_checked = 0
        else:
            ac_section_end_candidates = [
                body.find(h, ac_section_start)
                for h in ("### Verification", "### Code touch points", "## Story")
            ]
            ac_section_end_candidates = [c for c in ac_section_end_candidates if c != -1]
            ac_end = min(ac_section_end_candidates) if ac_section_end_candidates else len(body)
            ac_body = body[ac_section_start:ac_end]
            ac_marks = AC_BOX.findall(ac_body)
            ac_total = len(ac_marks)
            ac_checked = sum(1 for m in ac_marks if m in ("x", "X"))

        spec_raw = fields.get("Spec", "")
        spec_list = [s.strip() for s in spec_raw.split(",") if s.strip()] if spec_raw else []

        stories.append(
            Story(
                id=fields["ID"],
                file=path,
                status=fields["Status"],
                prerequisites=_parse_id_list(fields.get("Prerequisites", "[]")),
                unblocks=_parse_id_list(fields.get("Unblocks", "[]")),
                estimated_size=fields["Estimated size"],
                spec=spec_list,
                done_line=fields.get("Done"),
                acceptance_total=ac_total,
                acceptance_checked=ac_checked,
            )
        )
    return stories
