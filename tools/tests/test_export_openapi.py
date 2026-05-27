from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "backend" / "config" / "defaults" / "medicare_fraud.yaml"


def test_export_openapi_writes_deterministic_schema(tmp_path: Path) -> None:
    first = tmp_path / "openapi-a.json"
    second = tmp_path / "openapi-b.json"

    command = [
        sys.executable,
        "-m",
        "tools.export_openapi",
        "--config",
        str(DEFAULT_CONFIG),
        "--output",
        str(first),
    ]
    subprocess.run(command, cwd=ROOT, check=True)

    command[-1] = str(second)
    subprocess.run(command, cwd=ROOT, check=True)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_export_openapi_contains_frontend_contract_schemas(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.export_openapi",
            "--config",
            str(DEFAULT_CONFIG),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )

    schema = json.loads(output.read_text(encoding="utf-8"))
    components = schema["components"]["schemas"]
    paths = schema["paths"]

    assert "ChatConversationResponse" in components
    assert "DomainConfig" in components
    assert "Relationship" in components
    assert "/chat/conversations/{conversation_id}/messages" in paths


def test_export_openapi_forces_local_mode_when_environment_is_production(
    tmp_path: Path,
) -> None:
    output = tmp_path / "openapi.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.export_openapi",
            "--config",
            str(DEFAULT_CONFIG),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        env={**os.environ, "CHILI_ENV": "production"},
    )

    schema = json.loads(output.read_text(encoding="utf-8"))

    assert schema["openapi"]
    assert schema["info"]["title"] == "chiliAI API"
