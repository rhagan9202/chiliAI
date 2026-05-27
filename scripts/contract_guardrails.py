"""Static guardrails for frontend/backend contract alignment."""

from __future__ import annotations

import re
from pathlib import Path


GENERATED_HEADER = (
    "// Generated from backend OpenAPI. Do not edit by hand.\n"
    "// Run: npm run codegen:api\n"
)
SCHEMA_IMPORT_RE = re.compile(r"from ['\"].*lib/api/schema['\"]")
EXPORT_RE = re.compile(
    r"^\s*export\s+(?P<kind>type|interface)\s+(?P<name>[A-Za-z0-9_]+)\b(?P<rest>.*)$",
    re.MULTILINE,
)
GENERATED_COMPOSITION_RE = re.compile(
    r"=\s*(?:Schemas\[|RequireFields<|OptionalFields<|Omit<|Partial<|components\[)"
)
ALLOWED_MANUAL_EXPORTS = {"DomainConfigSchema", "RealtimeSnapshotResponse"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _is_test_path(path: Path) -> bool:
    return (
        "__tests__" in path.parts
        or "test" in path.parts
        or path.name.endswith((".test.ts", ".test.tsx"))
    )


def _check_contracts_file(contracts: Path) -> list[str]:
    errors: list[str] = []
    text = _read(contracts)

    if "components['schemas']" not in text:
        errors.append(f"{contracts}: must alias generated OpenAPI components['schemas']")

    for match in EXPORT_RE.finditer(text):
        kind = match.group("kind")
        name = match.group("name")
        rest = match.group("rest")
        line = _line_number(text, match.start())

        if name in ALLOWED_MANUAL_EXPORTS:
            continue
        if kind == "interface":
            errors.append(f"{contracts}:{line}: manual exported DTO is forbidden")
            continue
        if "{" in rest and not GENERATED_COMPOSITION_RE.search(rest):
            errors.append(f"{contracts}:{line}: manual exported DTO is forbidden")
            continue
        if "=" in rest and not GENERATED_COMPOSITION_RE.search(rest):
            errors.append(
                f"{contracts}:{line}: exported contract must compose generated OpenAPI schema"
            )

    return errors


def check_paths(root: Path) -> list[str]:
    errors: list[str] = []
    app = root / "chili_app"
    contracts = app / "src" / "api" / "contracts.ts"
    schema = app / "src" / "lib" / "api" / "schema.ts"
    package_json = app / "package.json"

    schema_text = _read(schema)
    if not schema_text.startswith(GENERATED_HEADER):
        errors.append(f"{schema}: missing generated OpenAPI header")

    package_text = _read(package_json)
    if "openapi-typescript ./openapi.json" not in package_text:
        errors.append(f"{package_json}: codegen:api must read checked-in ./openapi.json")
    if "ensure-generated-api-header.mjs" not in package_text:
        errors.append(f"{package_json}: codegen:api must restore generated schema header")

    errors.extend(_check_contracts_file(contracts))

    src = app / "src"
    if src.exists():
        for path in src.rglob("*.ts*"):
            if path == contracts or path == schema:
                continue
            text = _read(path)
            if SCHEMA_IMPORT_RE.search(text):
                errors.append(f"{path}: direct generated schema import is forbidden")
            if not _is_test_path(path) and ("as any" in text or "Record<string, any>" in text):
                errors.append(f"{path}: any-based API contract escape hatch is forbidden")

    return errors


def main() -> int:
    errors = check_paths(Path.cwd())
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
