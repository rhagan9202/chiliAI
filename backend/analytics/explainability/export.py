"""Render a persisted evidence pack as a portable document (UXA-405).

The evidence pack is the product's core explainability artifact, and until now
it could not leave the browser. Rendering lives here rather than in ``api/``
because this module owns evidence packs and the gateway holds no business
logic; one renderer also means the file an analyst downloads cannot drift from
what any other caller would get.

Rendered on demand rather than stored: the pack is already durable and this is
a deterministic projection of it, so a stored copy would only raise the
question of whether it is stale.
"""

from __future__ import annotations

from shared.types import EvidencePack

__all__ = ["humanize_score_name", "render_evidence_markdown"]


def humanize_score_name(name: str) -> str:
    """``peer_deviation`` -> ``Peer deviation``: score keys are data, not copy.

    Mirrors ``humanizeScoreName`` in ``EvidencePackViewer.tsx``. The two are
    duplicated across the wire on purpose — the export must read like the
    screen it came from — and a test asserts they agree on the shared cases.
    """
    words = name.replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else ""


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def render_evidence_markdown(
    pack: EvidencePack, *, alert_title: str | None = None
) -> str:
    """Render one evidence pack as Markdown.

    Empty collections are omitted rather than rendered as bare headings — a
    pack with no citations should not produce a "Source documents" section with
    nothing under it.
    """
    lines: list[str] = []
    heading = alert_title or f"Evidence pack {pack.id}"
    lines.append(f"# {heading}")
    lines.append("")
    lines.append(f"- **Evidence pack:** `{pack.id}`")
    lines.append(f"- **Alert:** `{pack.alert_id}`")
    lines.append(f"- **Generated:** {pack.created_at.isoformat()}")
    lines.append(f"- **Confidence:** {_percent(pack.confidence)}")
    lines.append("")

    if pack.reasoning.strip():
        lines.append("## Reasoning")
        lines.append("")
        lines.append(pack.reasoning.strip())
        lines.append("")

    for section in pack.narrative_sections:
        lines.append(f"## {section.heading}")
        lines.append("")
        lines.append(section.body.strip())
        if section.evidence_refs:
            lines.append("")
            lines.append(f"_Refs: {', '.join(section.evidence_refs)}_")
        lines.append("")

    if pack.scores:
        lines.append("## Scores")
        lines.append("")
        for name, value in sorted(pack.scores.items()):
            lines.append(f"- **{humanize_score_name(name)}:** {value}")
        lines.append("")

    if pack.attribution:
        lines.append("## Contributing factors")
        lines.append("")
        for item in pack.attribution:
            label = humanize_score_name(item.feature_name)
            # Signed: a factor that pushed the score *down* is as much a part
            # of the explanation as one that pushed it up.
            rendered = f"- **{label}:** {item.contribution:+.3f}"
            if item.rationale.strip():
                rendered = f"{rendered} — {item.rationale.strip()}"
            lines.append(rendered)
        lines.append("")

    if pack.source_documents:
        lines.append("## Source documents")
        lines.append("")
        for source in pack.source_documents:
            lines.append(f"- `{source}`")
        lines.append("")

    if pack.subgraph_nodes or pack.subgraph_edges:
        lines.append("## Subgraph")
        lines.append("")
        lines.append(f"- **Nodes:** {len(pack.subgraph_nodes)}")
        for node in pack.subgraph_nodes:
            lines.append(f"  - `{node}`")
        lines.append(f"- **Edges:** {len(pack.subgraph_edges)}")
        for edge in pack.subgraph_edges:
            lines.append(f"  - `{edge}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
