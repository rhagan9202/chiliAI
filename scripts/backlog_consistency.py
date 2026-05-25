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
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


STORY_HEADING = re.compile(r"^## Story (\S+):", re.MULTILINE)
FIELD = re.compile(r"^\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.*?)\s*$", re.MULTILINE)
AC_BOX = re.compile(r"^- \[(?P<mark>[ xX])\]", re.MULTILINE)
ID_LIST = re.compile(r"\[(?P<inner>[^\]]*)\]")
ID_RE = re.compile(r"^_?[a-z]+\.\d+$")


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

        story_id = fields["ID"]
        if not ID_RE.match(story_id):
            raise ValueError(f"Invalid ID format in {path}: {story_id!r}")

        stories.append(
            Story(
                id=story_id,
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


def _find_cycle(cyclic: list[str], stories: dict[str, Story]) -> list[str]:
    """Return one representative cycle within ``cyclic``.

    Uses an iterative DFS so we never blow the stack on deep graphs.
    """
    start = cyclic[0]
    path: list[str] = []
    on_path: set[str] = set()
    # Stack frames: (node, iterator-over-prereqs-still-in-cyclic)
    stack: list[tuple[str, list[str]]] = []
    cyclic_set = set(cyclic)

    def push(node: str) -> None:
        path.append(node)
        on_path.add(node)
        children = [p for p in stories[node].prerequisites if p in cyclic_set]
        stack.append((node, children))

    push(start)
    while stack:
        node, children = stack[-1]
        if not children:
            stack.pop()
            on_path.discard(node)
            path.pop()
            continue
        nxt = children.pop()
        if nxt in on_path:
            i = path.index(nxt)
            return path[i:]
        push(nxt)
    return [start]


def detect_cycles(stories: dict[str, Story]) -> list[list[str]]:
    """Return one representative cycle per disconnected cyclic component, or []."""
    in_deg: dict[str, int] = {sid: len(s.prerequisites) for sid, s in stories.items()}
    reverse: dict[str, list[str]] = defaultdict(list)
    for sid, story in stories.items():
        for p in story.prerequisites:
            if p in stories:
                reverse[p].append(sid)
    # Recompute in_deg to skip unresolved prereqs (otherwise everything is "cyclic")
    in_deg = {sid: 0 for sid in stories}
    for sid, story in stories.items():
        for p in story.prerequisites:
            if p in stories:
                in_deg[sid] += 1
    ready = [sid for sid, d in in_deg.items() if d == 0]
    visited: set[str] = set()
    while ready:
        sid = ready.pop()
        visited.add(sid)
        for child in reverse[sid]:
            in_deg[child] -= 1
            if in_deg[child] == 0:
                ready.append(child)
    cyclic = [sid for sid in stories if sid not in visited]
    if not cyclic:
        return []
    cycle = _find_cycle(cyclic, stories)
    return [cycle]


def validate_prereq_references(stories: dict[str, Story]) -> list[str]:
    """Return one error string per unresolved Prerequisites ID."""
    errors: list[str] = []
    for story in stories.values():
        for pid in story.prerequisites:
            if pid not in stories:
                errors.append(
                    f"Story {story.id} ({story.file.name}) cites prerequisite "
                    f"{pid!r} that does not exist"
                )
    return errors


def validate_status_invariants(stories: dict[str, Story]) -> list[str]:
    """Enforce status invariants.

    - ``done`` requires a Done line and all AC boxes checked.
    - ``in-progress`` requires all (resolved) prerequisites to be ``done``.
    - Status must be one of planned/in-progress/done/dropped.
    """
    errors: list[str] = []
    for s in stories.values():
        if s.status == "done":
            if not s.done_line:
                errors.append(f"Story {s.id}: Status=done but Done line is missing")
            if s.acceptance_total > 0 and s.acceptance_checked < s.acceptance_total:
                missing = s.acceptance_total - s.acceptance_checked
                errors.append(
                    f"Story {s.id}: Status=done but {missing} unchecked acceptance criteria"
                )
        if s.status == "in-progress":
            unmet = [
                p for p in s.prerequisites if p in stories and stories[p].status != "done"
            ]
            if unmet:
                errors.append(
                    f"Story {s.id}: Status=in-progress but not all prerequisites are done: {unmet}"
                )
        if s.status not in ("planned", "in-progress", "done", "dropped"):
            errors.append(f"Story {s.id}: invalid Status {s.status!r}")
    return errors


def compute_unblocks(stories: dict[str, Story]) -> dict[str, list[str]]:
    """Compute the inverse of Prerequisites: which stories does each story unblock?"""
    result: dict[str, list[str]] = {sid: [] for sid in stories}
    for s in stories.values():
        for p in s.prerequisites:
            if p in result:
                result[p].append(s.id)
    for k in result:
        result[k].sort()
    return result


def warn_xl_size(stories: dict[str, Story]) -> list[str]:
    """Return one warning per XL story — XL should be split before merge."""
    return [
        f"Story {s.id}: Estimated size XL — split before merge"
        for s in stories.values()
        if s.estimated_size == "XL"
    ]


def parse_all(backlog_dir: Path) -> dict[str, Story]:
    """Parse every ``*.md`` file in ``backlog_dir`` into an ID-keyed map.

    ``README.md`` is skipped. Duplicate IDs across files raise ``ValueError``.
    """
    result: dict[str, Story] = {}
    for path in sorted(backlog_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        for story in parse_file(path):
            if story.id in result:
                raise ValueError(
                    f"Duplicate ID {story.id} in {path} (also in {result[story.id].file})"
                )
            result[story.id] = story
    return result
