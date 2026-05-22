"""Materialize a Tennessee-filtered NPPES + DE-SynPUF subset for the demo."""

from __future__ import annotations

import argparse
import csv
import hashlib
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


_DESYNPUF_FILES: dict[str, tuple[str, str]] = {
    # output key -> (glob pattern, npi column name)
    "carrier_claims": ("DE1_0_2008_to_2010_Carrier_Claims_Sample_*.csv", "PRF_PHYSN_NPI_1"),
    "inpatient_claims": ("DE1_0_2008_to_2010_Inpatient_Claims_Sample_*.csv", "AT_PHYSN_NPI"),
    "outpatient_claims": ("DE1_0_2008_to_2010_Outpatient_Claims_Sample_*.csv", "AT_PHYSN_NPI"),
}


def _filter_desynpuf(config: BuildConfig, npi_set: set[str]) -> dict[str, int]:
    """Filter DE-SynPUF claim files and cross-filter beneficiaries."""

    tn_npis = sorted(npi_set)
    if not tn_npis:
        raise ValueError("Cannot filter DE-SynPUF without any TN NPIs.")

    counts: dict[str, int] = {}
    kept_beneficiary_ids: set[str] = set()

    for output_key, (pattern, npi_col) in _DESYNPUF_FILES.items():
        kept = 0
        output_path = config.output_root / f"desynpuf_{output_key}_tn.csv"
        files = sorted(glob(str(config.desynpuf_root / pattern)))
        if not files:
            counts[output_key] = 0
            continue

        writer: csv.DictWriter[str] | None = None
        dst_handle = output_path.open("w", encoding="utf-8", newline="")
        try:
            for source in files:
                with Path(source).open("r", encoding="utf-8", newline="") as src:
                    reader = csv.DictReader(src)
                    if reader.fieldnames is None:
                        continue
                    if writer is None:
                        writer = csv.DictWriter(dst_handle, fieldnames=reader.fieldnames)
                        writer.writeheader()
                    for row in reader:
                        keep = _apply_strategy(row, npi_col, tn_npis, config.strategy, npi_set)
                        if not keep:
                            continue
                        if config.sample_rate < 1.0:
                            seed = row.get("CLM_ID", "") + npi_col
                            score = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
                            if score >= config.sample_rate:
                                continue
                        if bene_id := row.get("DESYNPUF_ID"):
                            kept_beneficiary_ids.add(bene_id)
                        writer.writerow(row)
                        kept += 1
        finally:
            dst_handle.close()
        counts[output_key] = kept

    counts["beneficiaries"] = _filter_beneficiaries(config, kept_beneficiary_ids)
    return counts


def _apply_strategy(
    row: dict[str, str],
    npi_col: str,
    tn_npis: list[str],
    strategy: Strategy,
    npi_set: set[str],
) -> bool:
    """Decide whether to keep `row`; for remap/synthetic, mutate `row[npi_col]` in place.

    The mutated row is consumed immediately by the writer and then discarded, so the
    mutation is intentional and contained.
    """
    if strategy == "natural":
        return row.get(npi_col) in npi_set
    if strategy == "remap":
        original = row.get(npi_col, "")
        idx = int(hashlib.sha256(original.encode("utf-8")).hexdigest(), 16) % len(tn_npis)
        row[npi_col] = tn_npis[idx]
        return True
    if strategy == "synthetic":
        seed = row.get("CLM_ID", "") + npi_col
        idx = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(tn_npis)
        row[npi_col] = tn_npis[idx]
        return True
    raise ValueError(f"Unknown strategy: {strategy}")


def _filter_beneficiaries(config: BuildConfig, kept_ids: set[str]) -> int:
    pattern = str(config.desynpuf_root / "DE1_0_*_Beneficiary_Summary_File_Sample_*.csv")
    files = sorted(glob(pattern))
    if not files:
        return 0
    output_path = config.output_root / "desynpuf_beneficiaries_tn.csv"
    total_kept = 0
    writer: csv.DictWriter[str] | None = None
    dst_handle = output_path.open("w", encoding="utf-8", newline="")
    try:
        for source in files:
            with Path(source).open("r", encoding="utf-8", newline="") as src:
                reader = csv.DictReader(src)
                if reader.fieldnames is None:
                    continue
                if writer is None:
                    writer = csv.DictWriter(dst_handle, fieldnames=reader.fieldnames)
                    writer.writeheader()
                for row in reader:
                    if row.get("DESYNPUF_ID") in kept_ids:
                        writer.writerow(row)
                        total_kept += 1
    finally:
        dst_handle.close()
    return total_kept


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
