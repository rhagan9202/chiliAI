"""Architecture guardrails for vectorstore 1.0."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT
APPROVED_QDRANT_IMPORT_FILES = {
    BACKEND_ROOT / "vectorstore" / "adapters" / "qdrant_adapter.py",
    BACKEND_ROOT / "api" / "dependencies.py",
    BACKEND_ROOT / "agent" / "coordinator.py",
    BACKEND_ROOT / "tests" / "vectorstore" / "test_qdrant_adapter.py",
}
IGNORED_PARTS = {"__pycache__", ".venv", "chili_backend.egg-info"}


def test_qdrant_sdk_imports_stay_behind_adapter_boundary() -> None:
    offenders: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        if IGNORED_PARTS.intersection(path.parts) or path in APPROVED_QDRANT_IMPORT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "qdrant_client" or name.startswith("qdrant_client.") for name in names):
                offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == []
