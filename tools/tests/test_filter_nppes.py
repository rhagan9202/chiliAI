from __future__ import annotations

from pathlib import Path

from tools.sample_data.build_tennessee_subset import BuildConfig, filter_nppes


def test_filter_keeps_tn_only(tmp_path: Path) -> None:
    config = BuildConfig(
        nppes_root=Path(__file__).parent / "fixtures" / "nppes_micro",
        desynpuf_root=tmp_path,
        output_root=tmp_path,
    )
    npi_set = filter_nppes(config)
    assert len(npi_set) == 6
    assert (tmp_path / "nppes_providers_tn.csv").exists()
