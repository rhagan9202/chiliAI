# CONUS Air Force / Space Force Installations Reference

Canonical reference dataset for the Air Force housing dashboard. The tracked copy is
`installations_reference.csv` (this directory); the frontend mirror is
`chili_app/src/data/airForceInstallations.ts`. The two are kept identical (same
installation IDs and field values) and that agreement is enforced by
`chili_app/src/data/__tests__/airForceInstallations.test.ts`.

- **Compilation date:** 2026-07-06
- **Row count:** 65 (58 USAF, 7 USSF)
- **Coordinate datum:** WGS84 decimal degrees. Every row has coordinates (none blank).

## Inclusion rule

**In:** CONUS (contiguous 48 states + DC) major installations of the Department of the
Air Force with a resident host wing, delta, or named garrison equivalent, where the
Department of the Air Force is the installation owner or joint-base lead service:

- Active-duty USAF bases with a host wing (all MAJCOMs: ACC, AETC, AMC, AFGSC, AFMC,
  AFSOC), including AF-led joint bases (JB Langley-Eustis, JB San Antonio,
  JB Charleston, JB McGuire-Dix-Lakehurst, JB Andrews, JB Anacostia-Bolling).
- Direct Reporting Unit installations: US Air Force Academy (USAFA) and the two AFDW
  joint bases (AFDW remains a DRU as of 2026 — the circa-2020 proposal to fold it into
  AMC was never executed).
- AFRC-hosted **Air Reserve Bases** (Dobbins, Grissom, Homestead, March, Westover):
  AFRC owns these as full installations with host wings, so they carry DAF housing
  responsibility and are included.
- USSF major installations with a host delta (Space Base Delta / Space Launch Delta),
  plus Cape Canaveral SFS, which is the major spaceport half of the Patrick SFB
  complex under Space Launch Delta 45.
- Two named exceptions where the host unit is not a wing, kept because they are
  unambiguous stand-alone major installations: Arnold AFB (host unit is the Arnold
  Engineering Development Complex) and Hanscom AFB (host unit is the 66th Air Base
  Group).

**Out:**

- Annexes, ranges, and auxiliary fields (Gila Bend AFAF, Kegelman AFAF, Duke Field,
  Avon Park AF Range, Gunter Annex — folded into its Maxwell AFB row, Fort MacArthur —
  supported by Los Angeles AFB).
- **AFRC Air Reserve Stations** (Youngstown, Pittsburgh IAP, Niagara Falls,
  Minneapolis-St Paul): AFRC wings that are tenants on civil airports, not
  DAF-owned major installations.
- **ANG-hosted state bases** (all): operated by state Air National Guard on civil or
  state-owned fields; no active-component DAF installation ownership or MFH/UH housing
  responsibility. No sourced case emerged for any exception.
- **Army- or Navy-led joint bases** where the DAF is only a component: JB Lewis-McChord
  (Army lead; AMC's 62d Airlift Wing at McChord Field is a mission wing, not the
  installation host), Fort Meade, Pope Field (Army-owned; 43d AMOG is a tenant group).
- **USSF stations without their own host delta** — named installations that are
  geographically separated units supported from another base: Cheyenne Mountain SFS
  (supported by Space Base Delta 1/Peterson), New Boston SFS (Space Base Delta 41),
  Cape Cod SFS and Cavalier SFS (Space Base Delta 2), Pillar Point SFS (annex of
  Vandenberg).
- Non-CONUS DAF installations (Alaska, Hawaii, Greenland, overseas).

## ID conventions

`installation_id` is snake_case with a suffix per the official designation
(`_afb`, `_sfb`, `_sfs`, `_arb`); joint bases use a `jb_` prefix; `hurlburt_field` and
`usafa` follow their official names. Pre-existing fixture IDs `edwards_afb` and
`eglin_afb` are preserved unchanged (they are keys in the colocated housing sample
CSVs).

## Command vocabulary

- USAF `command` = MAJCOM (ACC, AETC, AMC, AFGSC, AFMC, AFSOC, AFRC) or DRU
  (AFDW, USAFA).
- USSF `command` = FLDCOM (SpOC, SSC). Note: SpOC was redesignated **Combat Forces
  Command (CFC)** on 3 Nov 2025; this dataset keeps the `SpOC` label per the frozen
  interface contract vocabulary. STARCOM HQ is relocating to Patrick SFB (2025–2027)
  but is a tenant there — Patrick's host remains Space Launch Delta 45 under SSC, so
  no row carries `STARCOM`.

## Recent realignments captured

- Holloman AFB: AETC → ACC on 4 Jun 2026 (recorded as ACC).
- Grand Forks AFB: AMC → ACC in 2019 (recorded as ACC).
- Kirtland AFB: AFMC → AFGSC on 1 Oct 2015 (recorded as AFGSC).
- Schriever SFB host: Space Base Delta 41 activated 18 Jun 2025 (replaces Space Base
  Delta 1 support).
- Luke AFB remains AETC as of July 2026; its 56th Fighter Wing FTU is slated for ACC
  reassignment (watch item, noted in its source_note).

## Sources

- Official installation and command pages: af.mil, base sites (`*.af.mil`,
  `*.afrc.af.mil`, `*.jb.mil`, jbsa.mil), spaceforce.mil and base sites
  (`petersonschriever.spaceforce.mil`, `buckley.spaceforce.mil`,
  `vandenberg.spaceforce.mil`, `patrick.spaceforce.mil`,
  `losangeles.spaceforce.mil`), MAJCOM sites (acc.af.mil, aetc.af.mil, amc.af.mil,
  afgsc.af.mil, afmc.af.mil, afsoc.af.mil, afrc.af.mil), afdw.af.mil, usafa.af.mil.
- Unit fact sheets cited per-row in `source_note` (e.g. Space Base Delta 1 fact sheet
  326192, Kirtland fact sheet 825944, D-M fact sheet 666235, af.mil article 2232606
  for the JBAB lead-service transfer, DVIDS 567007 for the Holloman reassignment).
- Cross-checks: Wikipedia "List of United States Air Force installations" and
  "List of United States Space Force installations"; airandspaceforces.com and
  breakingdefense.com for 2025–2026 USSF org changes.
- Coordinates: OurAirports open data
  (https://davidmegginson.github.io/ourairports-data/airports.csv), ident recorded in
  each `source_note`; Wikipedia/official coordinates for installations without an
  airfield (Schriever SFB, Los Angeles AFB, Joint Base Anacostia-Bolling) and for
  station centroids (Cape Canaveral SFS).

Each CSV row carries its own `source_note`. Fields are comma-free by construction so
the CSV parses with a plain split (asserted by the Vitest data-integrity test).

This is a public-reference research compilation for demo purposes, not an official
Department of the Air Force product.
