"""De-seed regression guard for BL-012.

Asserts that the previously-seeded ``ApiState`` data is no longer read from
non-test code paths: every removed ``_seed_*`` method / seeded attribute is
gone, and a tree scan finds no ``_seed_`` token in non-test backend modules.
"""

from __future__ import annotations

from pathlib import Path

import api.state as state_mod

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Methods + attributes removed from ApiState in BL-012.
_REMOVED_STATE_MEMBERS = (
    "_seed_graph",
    "_seed_alerts",
    "_seed_cases",
    "_seed_conversations",
    "_seed_evidence_packs",
    "_seed_workflows",
    "list_alerts",
    "get_alert_detail",
    "acknowledge_alert",
    "get_evidence_pack",
    "list_cases",
    "get_case_detail",
    "create_case",
    "update_case",
    "add_feedback",
    "list_workflows",
    "get_analytics_overview",
    "get_conversation",
    "create_conversation",
    "add_message",
    "get_graph_entity_detail",
)

_REMOVED_MODULE_SYMBOLS = ("ConversationRecord", "CaseRecord")


def test_removed_state_members_are_gone() -> None:
    for member in _REMOVED_STATE_MEMBERS:
        assert not hasattr(state_mod.ApiState, member), member
    for symbol in _REMOVED_MODULE_SYMBOLS:
        assert not hasattr(state_mod, symbol), symbol


def test_no_seed_token_in_non_test_backend_modules() -> None:
    offenders: list[str] = []
    for path in _BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(_BACKEND_ROOT)
        parts = rel.parts
        if parts[0] in {".venv", "tests"} or "migrations" in parts:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Strip the dev/e2e-only ``dev_seed`` endpoint references (those write
            # the durable stores; they are not the removed ApiState ``_seed_*``).
            scrubbed = line.replace("dev_seed", "").replace("dev-seed", "")
            if "_seed_" not in scrubbed:
                continue
            # The module docstring in api/state.py references the historical
            # ``_seed_*`` data only to explain that it is no longer read.
            if "``_seed_*``" in line:
                continue
            offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert offenders == [], offenders
