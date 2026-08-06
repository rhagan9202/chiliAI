"""chiliAI backlog consistency pass.

Parses the rich-format backlog stories under ``docs/backlog/``, validates
DAG/status invariants, computes Unblocks/ready-set/critical-path, and
rewrites the auto-generated marker sections in ``docs/backlog/README.md``.

Run as a script:

    python scripts/backlog_consistency.py [--backlog-dir DIR] [--check] [--strict]

Python 3.12 standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


STORY_HEADING = re.compile(r"^## Story (\S+):", re.MULTILINE)
FIELD = re.compile(r"^\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.*?)\s*$", re.MULTILINE)
AC_BOX = re.compile(r"^- \[(?P<mark>[ xX])\]", re.MULTILINE)
ID_LIST = re.compile(r"\[(?P<inner>[^\]]*)\]")
ID_RE = re.compile(r"^_?[a-z]+\.\d+$")
UNBLOCKS_LINE = re.compile(r"^\*\*Unblocks:\*\* \[[^\]]*\]\s*$", re.MULTILINE)


def _format_id_list(ids: list[str]) -> str:
    return "[" + ", ".join(ids) + "]"


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


SIZE_ORDER: dict[str, int] = {"S": 1, "M": 2, "L": 3, "XL": 4}
SIZE_WEIGHT: dict[str, int] = {"S": 1, "M": 2, "L": 5, "XL": 10}

MARKER_RE: dict[str, re.Pattern[str]] = {
    "status-rollup": re.compile(
        r"<!-- BEGIN: status-rollup -->.*?<!-- END: status-rollup -->", re.DOTALL
    ),
    "ready-set": re.compile(
        r"<!-- BEGIN: ready-set -->.*?<!-- END: ready-set -->", re.DOTALL
    ),
    "critical-path": re.compile(
        r"<!-- BEGIN: critical-path -->.*?<!-- END: critical-path -->", re.DOTALL
    ),
}


def render_status_rollup(stories: dict[str, Story]) -> str:
    """Render the per-file status rollup table."""
    by_file: dict[str, dict[str, int]] = defaultdict(
        lambda: {"planned": 0, "in-progress": 0, "done": 0, "dropped": 0}
    )
    for s in stories.values():
        by_file[s.file.name][s.status] += 1
    # Dropped is a real status and is counted in Total, so it needs its own
    # column: without it the Planned/In-progress/Done columns visibly fail to
    # sum to Total on any file that has dropped stories, which reads as an
    # arithmetic bug in the table rather than a missing category.
    lines = [
        "| File | Planned | In-progress | Done | Dropped | Total | % done |",
        "|------|---------|-------------|------|---------|-------|--------|",
    ]
    grand = {"planned": 0, "in-progress": 0, "done": 0, "dropped": 0}
    for fname in sorted(by_file):
        counts = by_file[fname]
        total = sum(counts.values())
        pct = (counts["done"] * 100 // total) if total else 0
        lines.append(
            f"| {fname} | {counts['planned']} | {counts['in-progress']} | "
            f"{counts['done']} | {counts['dropped']} | {total} | {pct}% |"
        )
        for k, v in counts.items():
            grand[k] += v
    gtotal = sum(grand.values())
    gpct = (grand["done"] * 100 // gtotal) if gtotal else 0
    lines.append(
        f"| **Total** | {grand['planned']} | {grand['in-progress']} | "
        f"{grand['done']} | {grand['dropped']} | {gtotal} | {gpct}% |"
    )
    return "\n".join(lines)


def render_ready_set(ready: list[Story]) -> str:
    """Render the ready set as a bullet list, capped at 30 entries."""
    capped = ready[:30]
    lines = [
        f"- [{s.id}] {s.file.stem} — size {s.estimated_size} — prereqs done"
        for s in capped
    ]
    if len(ready) > 30:
        lines.append(f"- …{len(ready) - 30} more")
    return "\n".join(lines) if lines else "- (no ready stories)"


def render_critical_path(path: list[Story]) -> str:
    """Render the critical path with per-step weights and total."""
    if not path:
        return "- (no path — DAG empty or contains a cycle)"
    total = sum(SIZE_WEIGHT.get(s.estimated_size, 1) for s in path)
    lines = [
        "> Longest dependency chain by weighted size (S=1, M=2, L=5, XL=10)."
    ]
    for i, s in enumerate(path, 1):
        w = SIZE_WEIGHT.get(s.estimated_size, 1)
        arrow = " →" if i < len(path) else ""
        lines.append(f"{i}. {s.id} ({s.estimated_size}={w}){arrow}")
    lines.append(f"\n**Total weight: {total}**")
    return "\n".join(lines)


def rewrite_readme(
    readme_path: Path,
    stories: dict[str, Story],
    check_only: bool,
) -> list[str]:
    """Rewrite the three auto-generated marker sections in the README.

    Returns the list of section names that changed.
    """
    text = readme_path.read_text(encoding="utf-8")
    ready = compute_ready_set(stories)
    crit = compute_critical_path(stories)
    sections = {
        "status-rollup": render_status_rollup(stories),
        "ready-set": render_ready_set(ready),
        "critical-path": render_critical_path(crit),
    }
    changes: list[str] = []
    new_text = text
    for name, body in sections.items():
        pat = MARKER_RE[name]
        if not pat.search(new_text):
            raise RuntimeError(f"README missing marker for {name}")
        replacement = f"<!-- BEGIN: {name} -->\n{body}\n<!-- END: {name} -->"
        patched = pat.sub(replacement, new_text)
        if patched != new_text:
            changes.append(name)
            new_text = patched
    if not check_only and new_text != text:
        readme_path.write_text(new_text, encoding="utf-8")
    return changes


def compute_critical_path(stories: dict[str, Story]) -> list[Story]:
    """Longest dependency chain by weighted size. Returns [] if a cycle is present."""
    in_deg: dict[str, int] = {sid: 0 for sid in stories}
    for s in stories.values():
        for p in s.prerequisites:
            if p in stories:
                in_deg[s.id] += 1
    reverse: dict[str, list[str]] = defaultdict(list)
    for s in stories.values():
        for p in s.prerequisites:
            if p in stories:
                reverse[p].append(s.id)
    order: list[str] = []
    ready = [sid for sid, d in in_deg.items() if d == 0]
    while ready:
        sid = ready.pop()
        order.append(sid)
        for child in reverse[sid]:
            in_deg[child] -= 1
            if in_deg[child] == 0:
                ready.append(child)
    if len(order) != len(stories):
        return []  # cycle present; caller should run detect_cycles separately
    best: dict[str, tuple[int, list[str]]] = {}
    for sid in order:
        s = stories[sid]
        w = SIZE_WEIGHT.get(s.estimated_size, 1)
        best_pred: tuple[int, list[str]] = (0, [])
        for p in s.prerequisites:
            if p in best and best[p][0] > best_pred[0]:
                best_pred = best[p]
        best[sid] = (best_pred[0] + w, best_pred[1] + [sid])
    if not best:
        return []
    _, path_ids = max(best.values(), key=lambda x: x[0])
    return [stories[i] for i in path_ids]


def compute_ready_set(stories: dict[str, Story]) -> list[Story]:
    """Return planned stories whose every prereq is done, sorted by size then ID."""
    ready: list[Story] = []
    for s in stories.values():
        if s.status != "planned":
            continue
        if all(p in stories and stories[p].status == "done" for p in s.prerequisites):
            ready.append(s)
    ready.sort(key=lambda s: (SIZE_ORDER.get(s.estimated_size, 99), s.id))
    return ready


def rewrite_unblocks(
    stories: dict[str, Story],
    computed: dict[str, list[str]],
    check_only: bool,
) -> list[str]:
    """Patch ``**Unblocks:** [...]`` lines to match ``computed``.

    Returns a list of human-readable change descriptions. If ``check_only`` is
    True, no file is written even when changes are detected.
    """
    changes: list[str] = []
    by_file: dict[Path, list[Story]] = defaultdict(list)
    for s in stories.values():
        by_file[s.file].append(s)
    for path, file_stories in by_file.items():
        text = path.read_text(encoding="utf-8")
        new_text = text
        for s in file_stories:
            expected = computed.get(s.id, [])
            if sorted(s.unblocks) == sorted(expected):
                continue
            heading = f"## Story {s.id}:"
            h_pos = new_text.find(heading)
            if h_pos == -1:
                raise RuntimeError(f"Could not find heading for {s.id} in {path}")
            ub_match = UNBLOCKS_LINE.search(new_text, h_pos)
            if not ub_match:
                raise RuntimeError(f"Could not find Unblocks line for {s.id} in {path}")
            old_line = ub_match.group(0)
            new_line = f"**Unblocks:** {_format_id_list(expected)}"
            new_text = new_text[: ub_match.start()] + new_line + new_text[ub_match.end():]
            changes.append(f"{path.name}:{s.id} {old_line.strip()} -> {new_line}")
        if new_text != text and not check_only:
            path.write_text(new_text, encoding="utf-8")
    return changes


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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Default mode rewrites Unblocks lines and README marker sections in place.
    ``--check`` is read-only: never writes, exits 1 on any drift or error.
    ``--strict`` promotes XL warnings to errors.

    Exit codes:
    - 0: clean (or non-check rewrites applied successfully)
    - 1: validation errors, drift in --check mode, or XL in --strict mode
    - 2: bad invocation (missing README)
    """
    parser = argparse.ArgumentParser(description="chiliAI backlog consistency pass")
    parser.add_argument(
        "--backlog-dir",
        default="docs/backlog",
        help="Directory containing backlog files",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only mode: exit non-zero on any drift; never write",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Upgrade XL warnings to errors",
    )
    args = parser.parse_args(argv)

    backlog_dir = Path(args.backlog_dir)
    readme = backlog_dir / "README.md"
    if not readme.exists():
        print(f"error: {readme} does not exist", file=sys.stderr)
        return 2

    stories = parse_all(backlog_dir)
    errors: list[str] = []
    errors.extend(validate_prereq_references(stories))
    cycles = detect_cycles(stories)
    for c in cycles:
        errors.append(f"Cycle detected: {' -> '.join(c)} -> {c[0]}")
    errors.extend(validate_status_invariants(stories))
    xl_warnings = warn_xl_size(stories)
    if args.strict:
        errors.extend(xl_warnings)

    computed = compute_unblocks(stories)
    unblocks_changes = rewrite_unblocks(stories, computed, check_only=args.check)
    readme_changes = rewrite_readme(readme, stories, check_only=args.check)

    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    for w in xl_warnings:
        if not args.strict:
            print(f"warning: {w}", file=sys.stderr)
    if args.check:
        for ch in unblocks_changes:
            print(f"drift: {ch}", file=sys.stderr)
        for name in readme_changes:
            print(f"drift: README section {name}", file=sys.stderr)
        if errors or unblocks_changes or readme_changes:
            return 1
    else:
        if errors:
            return 1
        for ch in unblocks_changes:
            print(f"rewrote: {ch}")
        for name in readme_changes:
            print(f"rewrote: README section {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
