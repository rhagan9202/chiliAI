# Air Force Housing Fixtures

Small file/export fixtures for the Department of the Air Force housing scorecard
workflow. Every feed fixture covers **all 65 CONUS installations** listed in
`installations_reference.csv` (see `INSTALLATIONS.md` for provenance and the
inclusion rule), one snapshot period (`2026-06-30`, most recent quarter end).

## Feed → file mapping

| Feed name (pack `records.feeds`) | Fixture file | Rows | Notes |
| --- | --- | --- | --- |
| `umd_authorizations` | `umd_sample.csv` | 1 per installation | Installation identity (name, MAJCOM/FLDCOM, state, coordinates, `branch`) + UH/MFH authorized demand |
| `bah_rates` | `bah_sample.csv` | 1 per installation | BAH rate, rentals, affordability index |
| `housing_inventory` | `inventory_sample.csv` | 2 per installation (UH + MFH) | Units, utilization, condition index, repair backlog / replacement cost / average unit age |
| `market_availability` | `market_sample.csv` | 1 per installation | Rental availability + affordability |
| `area_demographics` | `demographics_sample.csv` | 1 per installation | Local population + median income |
| `resident_experience` | `resident_experience_sample.csv` | 2 per installation (UH + MFH) | Satisfaction, maintenance response, work orders, disputes, safety waivers |

Reference (not a feed): `installations_reference.csv` + `INSTALLATIONS.md` —
the canonical installation set and IDs shared with the frontend module
`chili_app/src/data/airForceInstallations.ts`.

## Value calibration

Values are synthetic but plausible and deterministically calibrated against the
statutory scorecard thresholds so generated grades vary rather than being
uniform: roughly 45 installations are healthy (metrics pass), 14 are in a watch
band (warn), and 6 are in distress (fail) — e.g. condition index straddles the
80/60 pass/warn lines, UH/MFH supply ratios straddle 1.0/0.9, utilization
straddles the 0.9/0.75 bands, and resident satisfaction straddles 75/65.
`edwards_afb` is pinned to the watch band and `eglin_afb` to the healthy band,
preserving the character of the original two-installation fixture.

## Seeding and re-seeding

`tools/seed_housing_demo.py` (or `make seed-housing` with the stack running
under the housing pack) uploads these fixtures through the real records API
into a **fresh** knowledge base. Record ingestion is insert-only — rows are
keyed by record id, and re-uploading changed values into an existing KB
silently no-ops, so a scorecard re-run would grade stale data. After editing
fixture values, always seed a new KB (the script refuses to reuse a
same-named one) rather than re-uploading into an old one.

These are synthetic examples for local tests and demos. They are not official
Air Force data.
