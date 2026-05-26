from __future__ import annotations

from pathlib import Path

from scripts.contract_guardrails import check_paths


GENERATED_HEADER = (
    "// Generated from backend OpenAPI. Do not edit by hand.\n"
    "// Run: npm run codegen:api\n"
)


def _write_minimal_project(root: Path, contracts_text: str) -> Path:
    app = root / "chili_app"
    contracts = app / "src" / "api" / "contracts.ts"
    contracts.parent.mkdir(parents=True)
    contracts.write_text(contracts_text, encoding="utf-8")

    schema = app / "src" / "lib" / "api" / "schema.ts"
    schema.parent.mkdir(parents=True)
    schema.write_text(GENERATED_HEADER, encoding="utf-8")

    package_json = app / "package.json"
    package_json.write_text(
        '{"scripts":{"codegen:api":"openapi-typescript ./openapi.json --output src/lib/api/schema.ts && node scripts/ensure-generated-api-header.mjs"}}\n',
        encoding="utf-8",
    )
    return app


def test_guardrail_rejects_manual_contract_type(tmp_path: Path) -> None:
    _write_minimal_project(
        tmp_path,
        "export type FooResponse = { id: string }\n",
    )

    errors = check_paths(tmp_path)

    assert any("manual exported DTO" in error for error in errors)


def test_guardrail_accepts_generated_alias_contract(tmp_path: Path) -> None:
    _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type FooResponse = Schemas['FooResponse']\n",
    )

    assert check_paths(tmp_path) == []


def test_guardrail_accepts_generated_composition_contract(tmp_path: Path) -> None:
    _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "type RequireFields<T, K extends keyof T> = T & { [P in K]-?: NonNullable<T[P]> }\n"
        "export type FooResponse = RequireFields<Schemas['FooResponse'], 'items'>\n",
    )

    assert check_paths(tmp_path) == []


def test_guardrail_accepts_realtime_sse_exception(tmp_path: Path) -> None:
    _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type RealtimeSnapshotResponse = { sequence: number }\n",
    )

    assert check_paths(tmp_path) == []


def test_guardrail_accepts_domain_config_schema_exception(tmp_path: Path) -> None:
    _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type DomainConfigSchema = Record<string, unknown>\n",
    )

    assert check_paths(tmp_path) == []


def test_guardrail_rejects_generic_record_contract_export(tmp_path: Path) -> None:
    _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type FooResponse = Record<string, unknown>\n",
    )

    errors = check_paths(tmp_path)

    assert any("exported contract must compose generated OpenAPI schema" in error for error in errors)


def test_guardrail_rejects_direct_schema_import_outside_contracts(tmp_path: Path) -> None:
    app = _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type FooResponse = Schemas['FooResponse']\n",
    )
    offender = app / "src" / "pages" / "Bad.ts"
    offender.parent.mkdir(parents=True)
    offender.write_text("import type { components } from '../lib/api/schema'\n", encoding="utf-8")

    errors = check_paths(tmp_path)

    assert any("direct generated schema import" in error for error in errors)


def test_guardrail_rejects_missing_generated_header(tmp_path: Path) -> None:
    app = _write_minimal_project(
        tmp_path,
        "import type { components } from '../lib/api/schema'\n"
        "type Schemas = components['schemas']\n"
        "export type FooResponse = Schemas['FooResponse']\n",
    )
    (app / "src" / "lib" / "api" / "schema.ts").write_text(
        "export interface paths {}\n",
        encoding="utf-8",
    )

    errors = check_paths(tmp_path)

    assert any("missing generated OpenAPI header" in error for error in errors)
