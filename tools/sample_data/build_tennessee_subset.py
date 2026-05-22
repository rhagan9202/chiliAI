"""Materialize a Tennessee-filtered NPPES + DE-SynPUF subset for the demo."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Literal


Strategy = Literal["natural", "remap", "synthetic"]


@dataclass(frozen=True)
class BuildConfig:
    nppes_root: Path
    desynpuf_root: Path
    output_root: Path
    state_code: str = "TN"
    strategy: Strategy = "remap"
    sample_rate: float = 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Tennessee NPPES+DE-SynPUF subset.")
    parser.add_argument("--nppes-root", type=Path, default=Path("sample_data"))
    parser.add_argument("--desynpuf-root", type=Path, default=Path("sample_data/CMS"))
    parser.add_argument("--output-root", type=Path, default=Path("sample_data/CMS/tn_subset"))
    parser.add_argument("--state-code", default="TN")
    parser.add_argument("--strategy", choices=("natural", "remap", "synthetic"), default="remap")
    parser.add_argument("--sample-rate", type=float, default=1.0)
    args = parser.parse_args(argv)

    config = BuildConfig(
        nppes_root=args.nppes_root,
        desynpuf_root=args.desynpuf_root,
        output_root=args.output_root,
        state_code=args.state_code,
        strategy=args.strategy,
        sample_rate=args.sample_rate,
    )
    return build(config)


def build(config: BuildConfig) -> int:
    config.output_root.mkdir(parents=True, exist_ok=True)
    npi_set = _filter_nppes(config)
    claim_counts = _filter_desynpuf(config, npi_set)
    _write_manifest(config, npi_set, claim_counts)
    return 0


def _filter_nppes(config: BuildConfig) -> set[str]:
    """Stream-filter the NPPES master file to rows whose practice state matches."""

    npi_set: set[str] = set()
    state_field = "Provider Business Practice Location Address State Name"
    output_path = config.output_root / "nppes_providers_tn.csv"

    pattern = str(config.nppes_root / "npidata_pfile_*.csv")
    files = sorted(glob(pattern))
    if not files:
        raise FileNotFoundError(f"No NPPES file matched {pattern}")
    source_path = Path(files[0])

    with source_path.open("r", encoding="utf-8", newline="") as src, \
         output_path.open("w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        if reader.fieldnames is None:
            raise ValueError("NPPES file is missing a header row.")
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row.get(state_field) == config.state_code:
                writer.writerow(row)
                npi_set.add(row["NPI"])

    return npi_set


def _filter_desynpuf(config: BuildConfig, npi_set: set[str]) -> dict[str, int]:
    raise NotImplementedError("Implemented in Task 4.3")


def _write_manifest(
    config: BuildConfig,
    npi_set: set[str],
    claim_counts: dict[str, int],
) -> None:
    manifest = {
        "state_code": config.state_code,
        "strategy": config.strategy,
        "sample_rate": config.sample_rate,
        "npi_count": len(npi_set),
        "claim_counts": claim_counts,
    }
    (config.output_root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    sys.exit(main())
