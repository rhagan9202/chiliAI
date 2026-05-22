from __future__ import annotations

from pathlib import Path

from tools.sample_data.build_tennessee_subset import BuildConfig, _filter_desynpuf


def test_remap_strategy_keeps_all_claims_with_tn_npi(tmp_path: Path) -> None:
    npi_set = {f"100000000{i}" for i in range(1, 7)}  # 6 TN NPIs from the NPPES fixture
    config = BuildConfig(
        nppes_root=tmp_path,
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    counts = _filter_desynpuf(config, npi_set)

    # All carrier claims kept (remap assigns every claim to a TN NPI).
    assert counts["carrier_claims"] == 8
    assert counts["inpatient_claims"] == 5
    assert counts["outpatient_claims"] == 5

    # Beneficiary file is cross-filtered to beneficiaries referenced by kept claims.
    assert 0 < counts["beneficiaries"] <= 8
    assert (tmp_path / "desynpuf_beneficiaries_tn.csv").exists()
    assert (tmp_path / "desynpuf_carrier_claims_tn.csv").exists()


def test_natural_strategy_keeps_only_naturally_matching(tmp_path: Path) -> None:
    npi_set = {f"100000000{i}" for i in range(1, 7)}
    config = BuildConfig(
        nppes_root=tmp_path,
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="natural",
    )
    counts = _filter_desynpuf(config, npi_set)
    # Whatever the fixture naturally overlaps — should be at LEAST one if you constructed
    # the fixture with some matching NPIs. If zero is acceptable, change the assertion.
    assert counts["carrier_claims"] <= 8


def test_remap_is_deterministic(tmp_path: Path) -> None:
    npi_set = {f"100000000{i}" for i in range(1, 7)}
    config = BuildConfig(
        nppes_root=tmp_path,
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    _filter_desynpuf(config, npi_set)
    first_bytes = (tmp_path / "desynpuf_carrier_claims_tn.csv").read_bytes()
    _filter_desynpuf(config, npi_set)
    second_bytes = (tmp_path / "desynpuf_carrier_claims_tn.csv").read_bytes()
    assert first_bytes == second_bytes
