"""Architecture guards for embeddings module boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EMBEDDINGS_ROOT = BACKEND_ROOT / "embeddings"

FORBIDDEN_EMBEDDINGS_IMPORT_PREFIXES = (
    "analytics",
    "agent",
    "api",
    "graph",
    "vectorstore",
)

APPROVED_OPENAI_IMPORT_FILES = {
    BACKEND_ROOT / "embeddings" / "adapters" / "openai_adapter.py",
    BACKEND_ROOT / "llm" / "adapters" / "openai_adapter.py",
    BACKEND_ROOT / "tests" / "embeddings" / "test_openai_adapter.py",
}

APPROVED_SENTENCE_TRANSFORMERS_IMPORT_FILES = {
    BACKEND_ROOT / "embeddings" / "adapters" / "sentence_transformers_adapter.py",
    BACKEND_ROOT / "tests" / "embeddings" / "test_sentence_transformers_adapter.py",
}

IGNORED_PARTS = {
    ".venv",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "chili_backend.egg-info",
}


def test_embeddings_module_does_not_import_sibling_modules() -> None:
    offenders: list[str] = []
    for path in _python_files(EMBEDDINGS_ROOT):
        names = _imported_names(path)
        for name in names:
            if name in FORBIDDEN_EMBEDDINGS_IMPORT_PREFIXES or name.startswith(
                tuple(f"{prefix}." for prefix in FORBIDDEN_EMBEDDINGS_IMPORT_PREFIXES)
            ):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)} imports {name}")

    assert offenders == []


def test_provider_sdk_imports_stay_behind_adapters() -> None:
    openai_offenders: list[str] = []
    sentence_transformers_offenders: list[str] = []

    for path in _python_files(BACKEND_ROOT):
        names = _imported_names(path)
        if any(name == "openai" or name.startswith("openai.") for name in names):
            if path not in APPROVED_OPENAI_IMPORT_FILES:
                openai_offenders.append(str(path.relative_to(BACKEND_ROOT)))
        if any(
            name == "sentence_transformers" or name.startswith("sentence_transformers.")
            for name in names
        ):
            if path not in APPROVED_SENTENCE_TRANSFORMERS_IMPORT_FILES:
                sentence_transformers_offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert openai_offenders == []
    assert sentence_transformers_offenders == []


def test_import_scanner_detects_dynamic_imports(tmp_path: Path) -> None:
    module = tmp_path / "dynamic_imports.py"
    module.write_text(
        "\n".join(
            [
                "import importlib",
                "import pytest",
                'importlib.import_module("openai")',
                'pytest.importorskip("sentence_transformers")',
                '__import__("analytics.gnn")',
            ]
        ),
        encoding="utf-8",
    )

    assert {"openai", "sentence_transformers", "analytics.gnn"} <= _imported_names(
        module
    )


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if not any(part in IGNORED_PARTS for part in path.parts)
    ]


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
        elif isinstance(node, ast.Call):
            dynamic_name = _dynamic_import_name(node)
            if dynamic_name is not None:
                names.add(dynamic_name)
    return names


def _dynamic_import_name(node: ast.Call) -> str | None:
    if not node.args:
        return None
    if _call_name(node.func) not in {
        "__import__",
        "import_module",
        "importlib.import_module",
        "importorskip",
        "pytest.importorskip",
    }:
        return None
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return None


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return ""
