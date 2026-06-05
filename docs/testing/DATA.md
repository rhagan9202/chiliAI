# Test & Sample Data — the one place to look

> **Single source of truth** for where data lives in this repo and how devs/testers must use it.
> If you're about to add a CSV, a fixture, or wire up the live demo — read this first.

chiliAI's data falls into **two tiers**, and the rule is simple:

| Tier | Lives in | In git? | Size | Use it for |
|------|----------|---------|------|------------|
| **1. Tracked fixtures** | `backend/tests/**/fixtures/`, `tools/tests/fixtures/`, `docs/testing/knowledge_base_fixtures/` | ✅ committed | tiny (KB–MB) | unit tests, e2e tests, manual walkthroughs |
| **2. Local bulk source data** | `sample_data/` | ❌ **gitignored** | GB-scale | the live TN-subset demo + realistic manual ingest |

**Golden rules**
1. **Never commit bulk data.** Real CMS DE-SynPUF / NPPES files are GB-scale, public, and updated independently of this repo. `sample_data/` is gitignored (`sample_data/*` except its README). Runtime object-store data (`backend/data/`) is gitignored too.
2. **New test data → a tiny, purpose-built, tracked fixture** under the right `tests/.../fixtures/` dir (see the index below). Keep it synthetic — **no real PHI/PII/credentials**.
3. **Big realistic data stays local** in `sample_data/` and is staged by `make data-setup`.

---

## Quick start — make the stack live-test-ready

You need the public CMS archives downloaded once (see [Where to get the source data](#where-to-get-the-source-data)). Then:

```bash
# 1. Stage the downloaded zips into the canonical sample_data/ layout.
#    Override the source dir for your machine:
CMS_DOWNLOADS_DIR=/path/to/your/downloads make data-setup
#    (default source dir is /mnt/c/Users/rdhag/Downloads)

# 2. Bring up the full stack.
make dev          # wait for healthy

# 3. Build the Tennessee subset and ingest it through the real API.
make demo-tn-subset                          # sampled (DEMO_SAMPLE_RATE=0.01) — quick
# make tn-subset-full                        # the COMPLETE subset (~4.7M carrier claims / 2.4 GB) — slow, load-test scale
```

`make data-setup` is **idempotent** — it skips any file already staged, so it's safe to re-run.

> **Demo is sampled by default.** The full TN subset is ~4.7M carrier claims (2.4 GB) — too large to push through the API for a quick demo. `make demo-tn-subset` builds a `DEMO_SAMPLE_RATE` (default 1%) sample; override `DEMO_SAMPLE_RATE=1.0` or run `make tn-subset-full` for the complete set.

---

## Canonical layout (what the code expects)

The builder (`tools/sample_data/build_tennessee_subset.py`) and the demo
(`scripts/demo_ingest_tn_subset.sh`) read these exact paths. `make data-setup`
produces them:

```
sample_data/                                  # gitignored (bulk, local-only)
├── README.md                                 # tracked (the only tracked file here)
├── npidata_pfile_<dates>.csv                 # NPPES NPI registry (~11 GB)  ← builder --nppes-root
├── pl_pfile / othername_pfile / endpoint_pfile…   # NPPES aux (optional)
└── CMS/                                       # ← builder --desynpuf-root
    ├── DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv
    ├── DE1_0_2009_Beneficiary_Summary_File_Sample_1.csv
    ├── DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv
    ├── DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv
    ├── DE1_0_2008_to_2010_Outpatient_Claims_Sample_1.csv
    ├── DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.csv
    ├── DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.csv
    ├── DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_1.csv
    └── tn_subset/                             # ← builder --output-root (generated)
        ├── nppes_providers_tn.csv
        ├── desynpuf_inpatient_claims_tn.csv
        ├── desynpuf_outpatient_claims_tn.csv
        ├── desynpuf_carrier_claims_tn.csv
        ├── desynpuf_beneficiaries_tn.csv
        └── MANIFEST.json
```

> The `tn_subset/*.csv` files are the **TN-filtered, joined subset** the demo actually
> ingests — small enough to push through the API quickly while keeping production
> feed shapes. The demo uploads them to the `nppes_providers`, `inpatient_claims`,
> `outpatient_claims`, `carrier_claims_a`, and `beneficiary_2010` feeds defined in
> `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (the config the dev
> stack loads via `CHILI_CONFIG_PATH`).

---

## Fixture index — every data location and its consumer

| Location | Tier / git | What it is | Consumed by | Notes |
|----------|-----------|------------|-------------|-------|
| `sample_data/*.csv` | bulk · ignored | NPPES bulk pfiles | `tools/sample_data/build_tennessee_subset.py` (`--nppes-root`) | provider source for the TN subset |
| `sample_data/CMS/DE1_0_*.csv` | bulk · ignored | CMS DE-SynPUF samples | same builder (`--desynpuf-root`) | claims/beneficiary source |
| `sample_data/CMS/tn_subset/*.csv` | bulk · ignored | **generated** TN subset + `MANIFEST.json` | `scripts/demo_ingest_tn_subset.sh` (`make demo-tn-subset`) | output of the builder |
| `backend/tests/records/fixtures/cms/*_sample.csv` | tracked | tiny CMS samples (exact column layouts) | `backend/tests/records/test_cms_ingestion.py` | **column counts must match real CMS layouts** |
| `backend/tests/e2e/fixtures/tiny_*.csv` | tracked | tiny linked CMS rows (6 feeds) | `backend/tests/e2e/test_full_pipeline.py` | full records→graph→vector e2e |
| `backend/tests/ingestion/fixtures/policies/*` | tracked | synthetic policy corpus (MD/HTML/JSON/TXT/DOCX) | `test_full_pipeline.py` + `scripts/demo_ingest_tn_subset.sh` | document-ingestion / policy graph (BL-014) |
| `tools/tests/fixtures/{nppes_micro,desynpuf_micro}/*.csv` | tracked | micro NPPES + DE-SynPUF rows | `tools/tests/test_filter_nppes.py`, `test_filter_desynpuf.py`, `test_manifest_and_idempotency.py` | exercise the TN-subset builder |
| `docs/testing/knowledge_base_fixtures/medicare_fraud/*` | tracked | hand-crafted KB docs + `manifest.json` | manual / manifest-driven walkthroughs | expected graph counts + search queries; see its own README |
| `tests/scripts/fixtures/*.md` | tracked | backlog-story markdown | `tests/scripts/test_backlog_consistency.py` | **not data** — fixtures for the backlog tooling |
| `backend/data/` | runtime · ignored | local FS object-store (`base_path`) | the storage adapter at runtime | never commit |

**Where do I put a new fixture?**
- A records/CMS feed test → `backend/tests/records/fixtures/cms/` (match the real column layout).
- A full-pipeline e2e input → `backend/tests/e2e/fixtures/` (`tiny_*` naming; keep IDs linked across feeds).
- A document/policy doc → `backend/tests/ingestion/fixtures/policies/`.
- A TN-subset builder test → `tools/tests/fixtures/{nppes_micro,desynpuf_micro}/`.
- A manual KB walkthrough → `docs/testing/knowledge_base_fixtures/<domain>/` (+ update its `manifest.json`).
- **Bulk/realistic data → never a fixture; stage it locally in `sample_data/` via `make data-setup`.**

---

## Where to get the source data

All files are **public** CMS releases (synthetic — DE-SynPUF is CMS's de-identified synthetic Medicare PUF; NPPES is the public provider registry). Download once, drop the `.zip`s in one folder, point `CMS_DOWNLOADS_DIR` at it, and run `make data-setup`.

- **CMS DE-SynPUF** — CMS.gov → *Statistics, Trends & Reports → Medicare Claims Synthetic Public Use Files (DE-SynPUF)*. Grab `Sample_1` for: Beneficiary Summary (2008, 2009, 2010), Inpatient, Outpatient, Carrier (1A + 1B), Prescription Drug Events. (Carrier/PDE are ~100 MB zipped → ~1 GB each unzipped.)
- **NPPES NPI Registry** — CMS.gov → *NPPES Data Dissemination* monthly full file (`NPPES_Data_Dissemination_<Month>_<Year>.zip`, ~1 GB zipped → ~11 GB `npidata_pfile_*.csv`).

`make data-setup` extracts each archive's inner CSV into the canonical layout above; it leaves your downloads folder untouched.

---

## How `make data-setup` works

`scripts/setup_local_data.sh` (idempotent):
1. Reads `CMS_DOWNLOADS_DIR` (default `/mnt/c/Users/rdhag/Downloads`).
2. For each `*DE1_0_*Sample*.zip`, extracts its inner CSV (already cleanly named — numeric filename prefixes like `176541_` are stripped) into `sample_data/CMS/`, skipping any already present.
3. Ensures `sample_data/npidata_pfile_*.csv` exists, extracting it from the NPPES zip if missing.

To stage data on a fresh machine: download the archives → `CMS_DOWNLOADS_DIR=… make data-setup` → `make demo-tn-subset`.

---

## Known gap

PDF policy-corpus fixtures are not yet generated (no `pandoc` in the dev image); the corpus currently ships MD/HTML/JSON/TXT/DOCX. See `docs/superpowers/specs/notes/synthetic-policy-corpus.md`.
