"""Export the backend OpenAPI schema without starting an HTTP server."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, NoReturn, Protocol, cast

from fastapi import FastAPI


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_CONFIG = BACKEND / "config" / "defaults" / "medicare_fraud.yaml"


class _JsonSchemaModel(Protocol):
    @classmethod
    def model_json_schema(cls, *, ref_template: str) -> dict[str, Any]: ...


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Domain config path used while creating the FastAPI app.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="OpenAPI JSON output path.",
    )
    return parser.parse_args(argv)


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config_path = args.config.resolve()
    output_path = args.output.resolve()

    if not config_path.is_file():
        _fail(f"Config file not found: {config_path}")

    sys.path.insert(0, str(BACKEND))
    os.environ["CHILI_ENV"] = "local"
    os.environ["CHILI_CONFIG_PATH"] = str(config_path)

    create_app = cast(
        Callable[[], FastAPI],
        getattr(importlib.import_module("api.app"), "create_app"),
    )
    domain_config_type = cast(
        type[_JsonSchemaModel],
        getattr(importlib.import_module("config.schema"), "DomainConfig"),
    )

    schema = create_app().openapi()
    domain_config_schema = domain_config_type.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    domain_config_defs = domain_config_schema.pop("$defs", {})
    schema["components"]["schemas"].update(domain_config_defs)
    schema["components"]["schemas"]["DomainConfig"] = domain_config_schema

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
