"""Guard: every `tool.pyright.include` entry must point at something.

PR #99 deleted `api/routers/ws.py` and `tests/api/test_ws_router.py` but left
both in the include list. pyright says nothing about an include entry that
resolves to no files — it simply checks fewer files than the list implies, and
a shrinking scope is invisible.

That is the same shape as the defects this codebase keeps finding: a
declaration and its subject drifting apart, each side individually plausible.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]


def test_every_pyright_include_entry_exists() -> None:
    with (_BACKEND / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    include = config["tool"]["pyright"]["include"]
    assert isinstance(include, list)

    missing = [entry for entry in include if not (_BACKEND / str(entry)).exists()]

    assert not missing, (
        f"tool.pyright.include names paths that no longer exist, so the strict "
        f"scope silently shrank: {missing}"
    )
