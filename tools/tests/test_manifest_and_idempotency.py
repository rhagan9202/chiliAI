from __future__ import annotations

import json
from pathlib import Path

from tools.sample_data.build_tennessee_subset import BuildConfig, build


def test_manifest_captures_strategy_and_counts(tmp_path: Path) -> None:
    config = BuildConfig(
        nppes_root=Path(__file__).parent / "fixtures" / "nppes_micro",
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    assert build(config) == 0
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert manifest["state_code"] == "TN"
    assert manifest["strategy"] == "remap"
    assert manifest["npi_count"] == 6
    assert "carrier_claims" in manifest["claim_counts"]
    # The remap strategy keeps all 8 carrier_claims rows from the fixture:
    assert manifest["claim_counts"]["carrier_claims"] == 8


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    config = BuildConfig(
        nppes_root=Path(__file__).parent / "fixtures" / "nppes_micro",
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    build(config)
    first_bytes = (tmp_path / "nppes_providers_tn.csv").read_bytes()
    build(config)
    second_bytes = (tmp_path / "nppes_providers_tn.csv").read_bytes()
    assert first_bytes == second_bytes
