# Tooling Inventory

**Generated:** 2026-05-22 (merge commit `acae4ac`)

---

## `tools/sample_data/build_tennessee_subset.py`

**Purpose:** Filters and transforms full CMS source datasets into a Tennessee-provider subset suitable for local development and demo ingestion.

**Entry point:** `python -m tools.sample_data.build_tennessee_subset [options]`
(Also invoked by `make demo-tn-subset`)

**Inputs:**
- NPPES National Provider Identifier CSV (default: `sample_data/`)
- DE-SynPUF claims CSVs (default: `sample_data/CMS/`)

**Outputs:**
- Filtered subset written to `sample_data/CMS/tn_subset/` by default
- `MANIFEST.json` with metadata about each output file

**Key CLI arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `--nppes-root` | `sample_data/` | Path containing the NPPES CSV download |
| `--desynpuf-root` | `sample_data/CMS/` | Path containing DE-SynPUF CSVs |
| `--output-root` | `sample_data/CMS/tn_subset/` | Output directory |
| `--state-code` | `TN` | Two-letter state filter for NPPES |
| `--strategy` | `remap` | `natural` (keep real NPIs), `remap` (hash NPIs), `synthetic` (generate new NPIs) |
| `--sample-rate` | `1.0` | Fraction of Tennessee providers to include (deterministic) |

**Algorithm:**
1. `filter_nppes` — Read NPPES CSV, filter rows by `provider_business_practice_location_address_state_name == state_code`. Returns a set of NPIs.
2. `filter_desynpuf` — Cross-filter each DE-SynPUF file to only rows where `PRF_PHYSN_NPI_1` is in the NPI set.
3. `_apply_strategy` — Apply the selected NPI anonymization strategy.
4. `_filter_beneficiaries` — Further filter beneficiary rows to those referenced by kept claims.
5. `_write_manifest` — Write `MANIFEST.json` with file sizes and record counts.

**Dependencies:** Python stdlib only (csv, json, hashlib, argparse, pathlib)

---

## `scripts/demo_ingest_tn_subset.sh`

**Purpose:** Shell driver that runs a full demo ingestion flow: build the Tennessee subset (if not already present), then ingest NPPES providers + DE-SynPUF claims into a fresh Knowledge Base via the API.

**Usage:**
```bash
CHILI_API_URL=<url> ./scripts/demo_ingest_tn_subset.sh
```

The script takes no CLI arguments: the API URL comes from `CHILI_API_URL` (default `http://localhost:8000`) and the KB name is fixed (`"TN Demo"`). It is driven by `make demo-cms` / the demo tooling.

**Prerequisites:** API running on `:8000`, Tennessee subset already materialized or `make demo-tn-subset` run first.

---

## `scripts/smoke_graph_workflow.sh`

**Purpose:** End-to-end smoke test that exercises the full document ingestion pipeline from upload through graph readiness. Validates pipeline stages by polling the events stream.

**Usage:** `./scripts/smoke_graph_workflow.sh`

**Prerequisites:** Full dev stack running (`make dev`).

---

## `make` Targets (relevant to tooling)

| Target | Command | Purpose |
|--------|---------|---------|
| `make demo-tn-subset` | Builds Tennessee subset via `tools/sample_data/build_tennessee_subset.py` | Materialize local demo data |
| `make dev` | `docker compose -f docker-compose.dev.yaml up --build` | Start full dev stack |
| `make test` | host venv: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov` (against `chili_test`, never the dev DB) | Run backend test suite |
