#!/usr/bin/env bash
#
# setup_local_data.sh — stage the local CMS/NPPES source data the ingestion
# pipeline expects. Extracts the downloaded DE-SynPUF + NPPES archives into the
# canonical sample_data/ layout consumed by tools/sample_data/build_tennessee_subset.py
# and scripts/demo_ingest_tn_subset.sh. Idempotent: skips files already present.
#
# See docs/testing/DATA.md for the full data plan.
#
# Source of the downloaded archives (override for your machine):
#   CMS_DOWNLOADS_DIR=/path/to/downloads scripts/setup_local_data.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADS="${CMS_DOWNLOADS_DIR:-/mnt/c/Users/rdhag/Downloads}"
CMS_DIR="$REPO_ROOT/sample_data/CMS"
NPPES_GLOB="$REPO_ROOT/sample_data/npidata_pfile_*.csv"

echo "Repo:       $REPO_ROOT"
echo "Downloads:  $DOWNLOADS"
echo "CMS target: $CMS_DIR"
echo

if [ ! -d "$DOWNLOADS" ]; then
  echo "ERROR: downloads dir not found: $DOWNLOADS" >&2
  echo "Set CMS_DOWNLOADS_DIR to where the CMS/NPPES .zip files live." >&2
  exit 1
fi

mkdir -p "$CMS_DIR"

# --- DE-SynPUF: extract each DE1_0_*_Sample_*.zip's inner CSV into sample_data/CMS/
shopt -s nullglob
found_any=0
for zip in "$DOWNLOADS"/*DE1_0_*Sample*.zip; do
  found_any=1
  # inner CSV name (zips contain a single cleanly-named CSV; numeric filename
  # prefixes on the .zip do not affect the inner CSV name)
  inner="$(unzip -Z1 "$zip" | grep -i '\.csv$' | head -1 || true)"
  if [ -z "$inner" ]; then
    echo "skip (no csv inside): $(basename "$zip")"; continue
  fi
  if [ -f "$CMS_DIR/$inner" ]; then
    echo "exists, skip:  $inner"
  else
    echo "extracting:    $(basename "$zip") -> CMS/$inner"
    unzip -j -o -q "$zip" "$inner" -d "$CMS_DIR"
  fi
done
[ "$found_any" = 1 ] || echo "WARNING: no DE1_0_*Sample*.zip found in $DOWNLOADS"

# --- NPPES: ensure sample_data/npidata_pfile_*.csv exists (the builder reads it).
if compgen -G "$NPPES_GLOB" >/dev/null; then
  echo "NPPES ok:      $(basename "$(ls $NPPES_GLOB | head -1)")"
else
  nppes_zip="$(ls "$DOWNLOADS"/NPPES_Data_Dissemination_*.zip 2>/dev/null | head -1 || true)"
  if [ -n "$nppes_zip" ]; then
    echo "extracting NPPES npidata from $(basename "$nppes_zip") (large, ~11GB) ..."
    npi_inner="$(unzip -Z1 "$nppes_zip" | grep -iE '^npidata_pfile_.*\.csv$' | head -1)"
    unzip -j -o -q "$nppes_zip" "$npi_inner" -d "$REPO_ROOT/sample_data"
  else
    echo "WARNING: no NPPES file at sample_data/ and no NPPES zip in $DOWNLOADS"
  fi
fi

echo
echo "Done. CMS files now staged:"
ls -1 "$CMS_DIR"/*.csv 2>/dev/null | sed "s#$REPO_ROOT/##" || echo "  (none)"
echo
echo "Next: build the TN subset + run the demo with:  make demo-tn-subset"
