# CMS Fraud Demo (Sprint 2026-28 D1 / BL-051)

A scripted walkthrough of chiliAI's Medicare-fraud domain pack
(`medicare_fraud_cms_desynpuf`) against a real 1% sample of CMS's public
DE-SynPUF data, resampled to Tennessee. It exists so anyone — not just
whoever built the feature that sprint — can bring the stack up, load real
data, and walk the exact same path a presenter would, live.

## What's here

- **[`presenter-script.md`](./presenter-script.md)** — the ≤10-minute, 3-act
  walkthrough: Dashboard → Alert Feed → Investigation Workbench dossier
  (Signals / Network / Policy / Evidence tabs) → Policy workspace, plus an
  optional Act 3 live domain-pack switch to the Air Force housing pack.
  Every claim in it was checked against the running component code as of
  2026-07-23 — no mockup numbers, no unshipped capabilities.
- **[`../../chili_app/e2e/demo-walkthrough.spec.ts`](../../chili_app/e2e/demo-walkthrough.spec.ts)**
  — the Playwright spec that mechanically walks the same path (reference
  mode against seeded dev data by default; live mode against a real TN demo
  KB when one exists) so the script cannot silently drift from the product.
  *(Lands in Sprint 2026-28 D1 Task 4; if this link 404s, that task hasn't
  merged yet — the script above is still accurate on its own.)*

## Prerequisites

1. **Bring the stack up:**
   ```bash
   make dev
   ```
   This starts the API, worker, frontend, and infra (Postgres/TimescaleDB,
   Neo4j, Qdrant, Redis, MinIO) with the `medicare_fraud_cms_desynpuf` pack
   active by default (no `CHILI_CONFIG_PATH` override needed).

2. **Stage and ingest the demo data:**
   ```bash
   make demo-cms
   ```
   This one command: confirms the API is healthy, switches to the
   `medicare_fraud_cms_desynpuf` pack if it isn't already active, builds the
   1% TN subset from `sample_data/CMS` if it hasn't been built yet (requires
   `make data-setup` to have staged the raw CMS/NPPES source data first — see
   `docs/testing/DATA.md`), ingests it through the real records API, and
   polls a set of readiness probes (KB ready, alerts live, GNN clusters
   present, an evidence pack with a narrative, and Task 1's policy-rule
   packs firing) before printing a summary with the knowledge-base id and
   the exact URLs to open. **Use those printed URLs** — don't guess at
   routes, and don't reuse a stale entity id from a previous run.

   `make demo-cms` requires the stack to already be running; it never runs
   `docker compose` itself, and it fails loudly with the exact next command
   if the API isn't reachable.

3. Open the printed URLs in the browser and follow
   `presenter-script.md` scene by scene.

## Reset instructions

To start over from a clean slate:

```bash
make clean   # docker compose down -v — stops the stack AND removes all volumes
make dev
make demo-cms
```

**What `make clean` destroys:** every database volume (Postgres/TimescaleDB,
Neo4j, Qdrant, Redis, MinIO/object storage). That means every knowledge
base, every ingested claim/provider/beneficiary entity, every alert, every
evidence pack, every policy item, and the previously-built TN subset's
*ingested* state are gone. It does **not** delete the locally-built
`sample_data/CMS/tn_subset/` files on disk — `make demo-cms` detects the
existing `MANIFEST.json` and skips rebuilding the subset, so a reset only
costs you the ingest + analytics time, not the sampling time. If you want a
genuinely fresh sample (e.g. after changing `DEMO_SAMPLE_RATE`), delete
`sample_data/CMS/tn_subset/` yourself before re-running `make demo-cms`.

`make down` (no `-v`) stops the stack without touching volumes, if you just
want to pause and resume later without losing demo data.

## A note on domain-pack switching

The optional Act 3 scene switches the active pack live through the real
in-app **Pack Switcher** on the Configuration page (`Activate` →
`Confirm switch`, backed by `POST /config/switch`) — not a raw API call —
to `department_air_force_housing` and back. The switch-back target must be
`medicare_fraud_cms_desynpuf` specifically — not the bare `medicare_fraud.yaml`
pack, which depends on a separate dev-environment overlay file for its
storage connections that a live hot-swap does not apply. `make dev`'s
default `CHILI_CONFIG_PATH` is already `medicare_fraud_cms_desynpuf.yaml`, so
switching back returns you to exactly where the stack started.

**The Pack Switcher requires the backend `admin` RBAC role.** This is a
separate concept from the analyst/supervisor domain-config UI role used
elsewhere in the script (that one only affects nav/landing pages). By
default `make dev` runs with the anonymous user at `viewer`, and there is no
in-app way to elevate that mid-session — it must be set before the stack
starts:

```bash
CHILI_DEV_ANONYMOUS_ROLE=admin make dev
```

(the same mechanism `make test-e2e` uses with `=analyst`). Without it, the
Configuration page's "Pack switcher" section — and the "Pack editor" section
below it — simply do not render, and Act 3's live switch cannot be
demonstrated. If you're skipping Act 3, this is not needed; the rest of the
walkthrough works at the default `viewer`/`analyst` level.

## Keeping this demo honest

If you change a page, a rule pack, or an analytics capability that this
script or the e2e spec references, update both in the same change. The
constraint that makes this demo trustworthy is that every sentence in
`presenter-script.md` is true of the running product on the 1% TN subset —
treat a stale claim in it as a bug, not a documentation nit.
