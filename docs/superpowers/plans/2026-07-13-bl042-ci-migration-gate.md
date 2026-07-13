# BL-042 — CI Migration Drift / Replay Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CI-enforced gate proving that the full Alembic history replays cleanly against a fresh TimescaleDB (`upgrade head` → `downgrade base` → `upgrade head`) and that the resulting schema exactly matches a committed, normalized snapshot (`backend/database/migrations/snapshots/head.sql`).

**Architecture:** One POSIX bash script (`scripts/ci_migration_check.sh`) owns everything: it brings up only the compose `postgres` service (the same service-container pattern the CI backend job already proves), creates a *scratch* database `chili_migration_check` (never the dev `chili` DB), replays migrations via the project's Alembic, dumps a normalized `pg_dump --schema-only` of the `public` schema **from inside the container** (so pg_dump client version always equals server version), and either diffs it against the committed snapshot (check mode, fails loudly with a unified diff) or rewrites the snapshot (`--update-snapshot`, re-runnable — this is how the snapshot gets refreshed when BL-041's migration 0009 lands). A `make migrate-check` / `make migrate-snapshot` pair gives local parity, and a new independent CI job runs the same script.

**Tech Stack:** bash (`set -euo pipefail`), Alembic ≥1.13 + psycopg3 (backend `[postgres]` extra), `timescale/timescaledb:latest-pg16` compose service, pg_dump/psql executed via `docker compose exec -T postgres`, GitHub Actions.

## Global Constraints

- The script must be **idempotent** (scratch DB is force-dropped and recreated every run) and **fail loudly with a `diff -u` on drift** (exit 1).
- Local `make migrate-check` must **never touch the dev stack's main `chili` database** — all work happens in scratch DB `chili_migration_check`; the script hard-refuses `MIGRATE_CHECK_DB=chili` (exit 2).
- CI additions must keep all existing jobs (`backend`, `api-contracts`, `frontend`, `backlog`) **byte-for-byte untouched** — the new `migrations` job is independent (no `needs:`, no edits to other jobs).
- The snapshot is **content-based**: no Alembic revision IDs appear anywhere in it (`alembic_version` is excluded from the dump). This deliberately avoids worsening the docs-stories database.08–.13 revision-ID collision (0004..0008 literals) — this plan does NOT fix those docs.
- `DATABASE_URL` must be set **per-command only, never exported** — exporting it into a shell that later runs backend pytest wipes that database (`tests/database/test_migrations.py` runs `alembic downgrade base` against whatever `DATABASE_URL` points at).
- Migration 0009 (BL-041) has NOT landed on this branch yet — the snapshot ships at head = `0008_scorecards`; Task 7 refreshes it if/when 0009 exists, and the README (Task 6) makes "refresh snapshot in every migration PR" the standing rule.
- **Full CI verification (pushing and watching the workflow run) happens in the MAIN session at sprint verification — not inside these implementation tasks.** Tasks here verify locally plus YAML-parse the workflow.
- Verification steps need the Docker daemon running (Docker Desktop / WSL integration). It was down during planning (`/usr/bin/docker: Input/output error`) — start it before Task 2.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (repo rule).

## Investigation Facts (verified 2026-07-12, branch `feat/sprint-2026-26-ingestion-visibility`)

- All 8 migrations `0001`–`0008` in `backend/database/migrations/versions/` implement real raw-SQL `downgrade()` (DROP TABLE/INDEX/COLUMN `IF EXISTS`) — **no downgrade fixes needed**. `0001`'s downgrade does *not* drop the `timescaledb` extension; harmless, since the snapshot only covers `public`-schema objects and pg_dump auto-excludes extension-owned objects.
- `backend/alembic.ini` exists; `backend/database/migrations/env.py` reads `DATABASE_URL` (required, no default) and normalizes `postgresql://` → `postgresql+psycopg://`. Alembic must run with cwd `backend/`.
- Head `0008` schema = 12 tables: `raw_records`, `observations` (hypertable), `entity_metric_history` (hypertable), `entity_metrics_current`, `risk_score_history`, `alert_history`, `cases`, `policy_items`, `record_submissions`, `conversations`, `entity_derived_signals`, `scorecard_runs`.
- Compose `postgres` service (`docker-compose.dev.yaml:158`): image `timescale/timescaledb:latest-pg16`, `shared_preload_libraries=timescaledb` (cluster-wide — the extension works in any DB in that container), `POSTGRES_DB/USER/PASSWORD=chili`, published `5432:5432`, healthcheck `pg_isready`.
- CI backend job (`.github/workflows/ci.yml:65-71,86-87`) proves the pattern: `docker compose -f docker-compose.dev.yaml up -d --wait <services>` then `alembic upgrade head` with job-level `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili`. Teardown: `docker compose -f docker-compose.dev.yaml down -v` with `if: always()`.
- `alembic`, `psycopg[binary]`, `psycopg-pool` are the backend `[postgres]` extra (`backend/pyproject.toml:71-75`).
- `backend/tests/database/test_migrations.py` already exercises downgrade base / upgrade head as `@pytest.mark.integration` pytest — the CI gate is **not** a pytest duplicate; it adds fresh-DB replay + snapshot drift, so no new pytest file is added.
- pg_dump nondeterminism sources to normalize: `-- Dumped from/by ... version` header comments; `\restrict <random-token>` / `\unrestrict` psql meta-lines (added by the 2025 pg_dump security fix, present in current 16.x point releases — random per run); `SET ...` / `SELECT pg_catalog.set_config(...)` preamble (varies across point versions). Object ordering within a pg_dump of an identical schema is deterministic.
- `docker ps` etc. currently fail (daemon down) — start Docker before running any verification step below.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/ci_migration_check.sh` | Create | The entire gate: scratch-DB lifecycle, replay, normalized dump, diff / snapshot rewrite |
| `backend/database/migrations/snapshots/head.sql` | Create (generated) | Committed normalized schema snapshot at migration head |
| `Makefile` | Modify | `migrate-check` + `migrate-snapshot` targets (after `migrate:`, line 44) |
| `.github/workflows/ci.yml` | Modify (append only) | New independent `migrations` job |
| `backend/database/README.md` | Modify | Document the gate, the snapshot-refresh rule, and the downgrade contract |

---

### Task 1: The gate script `scripts/ci_migration_check.sh`

**Files:**
- Create: `scripts/ci_migration_check.sh` (mode `755`)

**Interfaces:**
- Produces: `scripts/ci_migration_check.sh [--update-snapshot|-h|--help]`; env overrides `MIGRATE_CHECK_DB` (scratch DB name, default `chili_migration_check`), `SNAPSHOT_PATH` (default `backend/database/migrations/snapshots/head.sql`). Exit codes: `0` clean, `1` replay failure or drift, `2` usage/environment error. Tasks 2–7, the Makefile, and CI all consume exactly this surface.

- [ ] **Step 1: Run the failing "tests" first (script doesn't exist yet)**

Run (from repo root `/home/rdhagan92/chiliAI`):
```bash
scripts/ci_migration_check.sh --help; echo "exit=$?"
MIGRATE_CHECK_DB=chili scripts/ci_migration_check.sh; echo "exit=$?"
```
Expected: both print `No such file or directory` and `exit=127`.

- [ ] **Step 2: Write the script**

Create `scripts/ci_migration_check.sh` with exactly this content:

```bash
#!/usr/bin/env bash
# ci_migration_check.sh — migration replay + schema-drift gate (BL-042 / database.04).
#
# Replays the full Alembic history against a FRESH scratch database on the
# dev-compose TimescaleDB service (upgrade head -> downgrade base -> upgrade
# head), then compares a normalized schema-only pg_dump of the result against
# the committed snapshot backend/database/migrations/snapshots/head.sql.
#
# The dev stack's main "chili" database is never touched: all work happens in
# a scratch database (default: chili_migration_check) that is force-dropped
# and recreated on every run, so the script is idempotent.
#
# pg_dump runs INSIDE the postgres container so the client version always
# matches the server. Output is normalized for determinism: SQL comments
# (-- Dumped from/by version headers), psql meta-commands (\restrict and
# \unrestrict carry a random token per dump), the SET/set_config preamble,
# and blank lines are stripped. alembic_version is excluded, so the snapshot
# is content-based and contains no Alembic revision IDs.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/ci_migration_check.sh [--update-snapshot]

  (no args)          Check mode: replay migrations on a scratch TimescaleDB
                     and diff the resulting schema against the committed
                     snapshot. Exits 1 with a unified diff on drift.
  --update-snapshot  Regenerate backend/database/migrations/snapshots/head.sql
                     from the replayed schema (re-runnable; run this in every
                     PR that adds or edits a migration, then commit the file).

Environment overrides:
  MIGRATE_CHECK_DB   Scratch database name (default: chili_migration_check).
                     "chili" is refused -- the dev database is never touched.
  SNAPSHOT_PATH      Snapshot file to compare or write
                     (default: backend/database/migrations/snapshots/head.sql).

Exit codes: 0 = clean, 1 = replay failure or schema drift, 2 = usage/env error.
EOF
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "${REPO_ROOT}/docker-compose.dev.yaml")
SCRATCH_DB="${MIGRATE_CHECK_DB:-chili_migration_check}"
SNAPSHOT_PATH="${SNAPSHOT_PATH:-${REPO_ROOT}/backend/database/migrations/snapshots/head.sql}"
PG_USER="chili"
# Published host port of the compose postgres service (docker-compose.dev.yaml).
SCRATCH_URL="postgresql://chili:chili@localhost:5432/${SCRATCH_DB}"

MODE="check"
case "${1:-}" in
  "") ;;
  --update-snapshot) MODE="update" ;;
  -h|--help) usage; exit 0 ;;
  *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac

if [[ "${SCRATCH_DB}" == "chili" ]]; then
  echo "ERROR: refusing to run against the dev database 'chili'." >&2
  echo "Set MIGRATE_CHECK_DB to a scratch name (default: chili_migration_check)." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "ERROR: docker daemon unavailable -- the scratch TimescaleDB runs on the" >&2
  echo "compose postgres service. Start Docker Desktop / the docker service." >&2
  exit 2
fi

if [[ -x "${REPO_ROOT}/backend/.venv/bin/alembic" ]]; then
  ALEMBIC="${REPO_ROOT}/backend/.venv/bin/alembic"
elif command -v alembic >/dev/null 2>&1; then
  ALEMBIC="$(command -v alembic)"
else
  echo "ERROR: alembic not found. Install it via the backend [postgres] extra," >&2
  echo "e.g. pip install -e 'backend[postgres]' (CI) or the backend/.venv (local)." >&2
  exit 2
fi

# Cluster-level statements (CREATE/DROP DATABASE) run connected to the
# always-present 'postgres' maintenance database -- never to 'chili'.
admin_psql() {
  "${COMPOSE[@]}" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${PG_USER}" -d postgres -Atc "$1"
}

scratch_psql() {
  "${COMPOSE[@]}" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${PG_USER}" -d "${SCRATCH_DB}" -Atc "$1"
}

# DATABASE_URL is scoped to each alembic invocation and NEVER exported:
# an exported DATABASE_URL pointing at a real database would be wiped by a
# later host pytest run (tests/database/test_migrations.py downgrades base).
alembic_cmd() {
  (cd "${REPO_ROOT}/backend" && DATABASE_URL="${SCRATCH_URL}" "${ALEMBIC}" "$@")
}

echo "==> starting compose postgres service (scratch db: ${SCRATCH_DB})"
"${COMPOSE[@]}" up -d --wait postgres

cleanup() {
  admin_psql "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> recreating scratch database ${SCRATCH_DB}"
admin_psql "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)" >/dev/null
admin_psql "CREATE DATABASE ${SCRATCH_DB}" >/dev/null

echo "==> alembic upgrade head (fresh database)"
alembic_cmd upgrade head

echo "==> alembic downgrade base"
alembic_cmd downgrade base

leftovers="$(scratch_psql "SELECT table_name FROM information_schema.tables \
  WHERE table_schema = 'public' AND table_name <> 'alembic_version' \
  ORDER BY table_name")"
if [[ -n "${leftovers}" ]]; then
  echo "FAIL: alembic downgrade base left objects behind in schema 'public':" >&2
  echo "${leftovers}" >&2
  echo "Every migration must implement a complete downgrade()." >&2
  exit 1
fi

echo "==> alembic upgrade head (replay)"
alembic_cmd upgrade head

echo "==> dumping normalized schema"
tmp_dump="$(mktemp)"
{
  # pg_dump runs inside the container: client version == server version.
  # --schema=public keeps extension internals (_timescaledb_*) out; pg_dump
  # auto-excludes extension-owned objects (the timescaledb functions) too.
  "${COMPOSE[@]}" exec -T postgres pg_dump \
      --schema-only --no-owner --no-privileges \
      --schema=public --exclude-table=public.alembic_version \
      -U "${PG_USER}" -d "${SCRATCH_DB}" \
    | sed -e '/^--/d' \
          -e '/^\\/d' \
          -e '/^SET /d' \
          -e '/^SELECT pg_catalog\.set_config/d' \
          -e '/^[[:space:]]*$/d'
  # Hypertable registrations live in the timescaledb catalog, not in the
  # public-schema DDL -- capture them in a deterministic footer.
  echo "-- timescaledb hypertables (hypertable_name|num_dimensions)"
  scratch_psql "SELECT hypertable_name || '|' || num_dimensions \
    FROM timescaledb_information.hypertables ORDER BY hypertable_name"
} > "${tmp_dump}"

if [[ "${MODE}" == "update" ]]; then
  mkdir -p "$(dirname "${SNAPSHOT_PATH}")"
  cp "${tmp_dump}" "${SNAPSHOT_PATH}"
  rm -f "${tmp_dump}"
  echo "OK: snapshot written: ${SNAPSHOT_PATH}"
  exit 0
fi

if [[ ! -f "${SNAPSHOT_PATH}" ]]; then
  echo "FAIL: snapshot ${SNAPSHOT_PATH} does not exist." >&2
  echo "Generate it with: scripts/ci_migration_check.sh --update-snapshot" >&2
  exit 1
fi

if ! diff -u "${SNAPSHOT_PATH}" "${tmp_dump}"; then
  cat >&2 <<'EOF'

FAIL: schema drift between the committed snapshot and the migrated schema.
(diff above: -committed snapshot / +schema produced by the migrations)

  * If you intentionally added or changed a migration, regenerate the
    snapshot and commit it with your migration:
        make migrate-snapshot
  * Otherwise, an existing migration no longer produces the schema it used
    to -- fix the migration; do NOT regenerate the snapshot to make CI green.
EOF
  rm -f "${tmp_dump}"
  exit 1
fi

rm -f "${tmp_dump}"
echo "OK: migration replay clean; schema matches ${SNAPSHOT_PATH}"
```

Then make it executable:
```bash
chmod +x /home/rdhagan92/chiliAI/scripts/ci_migration_check.sh
```

- [ ] **Step 3: Syntax-check and (if available) shellcheck**

Run:
```bash
bash -n /home/rdhagan92/chiliAI/scripts/ci_migration_check.sh; echo "exit=$?"
command -v shellcheck >/dev/null && shellcheck /home/rdhagan92/chiliAI/scripts/ci_migration_check.sh || echo "shellcheck not installed - skipped"
```
Expected: `exit=0`; shellcheck (if present) reports no errors. Fix any finding before proceeding — do not suppress.

- [ ] **Step 4: Verify the docker-free guard behaviors (no daemon needed)**

Run (from repo root):
```bash
scripts/ci_migration_check.sh --help; echo "exit=$?"
scripts/ci_migration_check.sh --bogus; echo "exit=$?"
MIGRATE_CHECK_DB=chili scripts/ci_migration_check.sh; echo "exit=$?"
```
Expected:
- `--help` prints the usage block, `exit=0`.
- `--bogus` prints `ERROR: unknown argument: --bogus` + usage to stderr, `exit=2`.
- `MIGRATE_CHECK_DB=chili` prints `ERROR: refusing to run against the dev database 'chili'.`, `exit=2` (the guard fires before any docker call).

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add scripts/ci_migration_check.sh
git commit -m "feat(database): add migration replay + schema-drift gate script (BL-042)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Generate and commit the schema snapshot

**Files:**
- Create (generated): `backend/database/migrations/snapshots/head.sql`

**Interfaces:**
- Consumes: `scripts/ci_migration_check.sh --update-snapshot` (Task 1).
- Produces: committed `backend/database/migrations/snapshots/head.sql` — the drift baseline every later task and CI compares against.

- [ ] **Step 1: Ensure the Docker daemon is running**

Run:
```bash
docker info >/dev/null && echo "docker OK"
```
Expected: `docker OK`. If it fails with an I/O or connection error, start Docker Desktop (WSL integration) and retry. Do not proceed without it.

- [ ] **Step 2: Generate the snapshot (this IS the re-runnable command AC-4 requires)**

Run (from repo root):
```bash
scripts/ci_migration_check.sh --update-snapshot; echo "exit=$?"
```
Expected output (order): `==> starting compose postgres service...`, `==> recreating scratch database chili_migration_check`, `==> alembic upgrade head (fresh database)`, `==> alembic downgrade base`, `==> alembic upgrade head (replay)`, `==> dumping normalized schema`, `OK: snapshot written: /home/rdhagan92/chiliAI/backend/database/migrations/snapshots/head.sql`, `exit=0`.

If `alembic upgrade head` fails or the leftover-table check trips, that is a real migration bug — stop and fix the migration (per CLAUDE.md, no known error may be left standing). Investigation found none expected: all of 0001–0008 have complete downgrades.

- [ ] **Step 3: Assert snapshot content is complete and normalized**

Run:
```bash
S=/home/rdhagan92/chiliAI/backend/database/migrations/snapshots/head.sql
grep -c '^CREATE TABLE' "$S"
grep -Ec 'Dumped (from|by)|^\\|^SET |set_config' "$S"
grep -A3 'timescaledb hypertables' "$S"
grep -c 'alembic_version' "$S"
```
Expected:
- Line 1: `12` CREATE TABLE statements (raw_records, observations, entity_metric_history, entity_metrics_current, risk_score_history, alert_history, cases, policy_items, record_submissions, conversations, entity_derived_signals, scorecard_runs).
- Line 2: `0` — no volatile lines (no pg_dump version headers, no `\restrict` tokens, no SET preamble). Note: `grep -c` prints `0` and exits 1 when there are no matches — that non-zero exit is the expected success signal here.
- Footer: `-- timescaledb hypertables (hypertable_name|num_dimensions)` followed by `entity_metric_history|1` and `observations|1`.
- Last line: `0` `alembic_version` mentions (again exit 1 from grep is expected) — AC-5: content-based snapshot, no revision-ID coupling.

- [ ] **Step 4: Prove the generator is deterministic (re-run, expect no diff)**

Run:
```bash
cd /home/rdhagan92/chiliAI
scripts/ci_migration_check.sh --update-snapshot
git diff --exit-code backend/database/migrations/snapshots/head.sql; echo "exit=$?"
```
Expected: `exit=0` — a second generation run produces a byte-identical file. If it differs, a volatile line escaped normalization: diff the two versions, extend the `sed` filter in `scripts/ci_migration_check.sh` for that specific line pattern, and repeat this step until stable.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/database/migrations/snapshots/head.sql
git commit -m "feat(database): commit normalized schema snapshot at head 0008 (BL-042)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Prove check mode — clean pass and loud drift failure

**Files:** none created or modified (tampered snapshot copy lives in the session scratchpad, outside the repo).

**Interfaces:**
- Consumes: `scripts/ci_migration_check.sh` check mode + `SNAPSHOT_PATH` override (Task 1); committed `head.sql` (Task 2).

- [ ] **Step 1: Clean state — expect exit 0**

Run (from repo root):
```bash
scripts/ci_migration_check.sh; echo "exit=$?"
```
Expected: the full replay sequence, then `OK: migration replay clean; schema matches .../snapshots/head.sql`, `exit=0`.

- [ ] **Step 2: Deliberately drifted state — expect exit 1 with a unified diff**

Tamper a *copy* of the snapshot (equivalent to the backlog's "mutate 0001 without updating head.sql" verification, but without touching repo files) by deleting the `risk_score_history` CREATE TABLE line:
```bash
PAD=/tmp/claude-1000/-home-rdhagan92-chiliAI/01429c3d-7b34-4c3f-bbcb-fbc0c854ce6b/scratchpad
mkdir -p "$PAD"
grep -v 'CREATE TABLE public.risk_score_history' \
  /home/rdhagan92/chiliAI/backend/database/migrations/snapshots/head.sql > "$PAD/tampered_head.sql"
cd /home/rdhagan92/chiliAI
SNAPSHOT_PATH="$PAD/tampered_head.sql" scripts/ci_migration_check.sh; echo "exit=$?"
```
Expected: a `diff -u` block showing `+CREATE TABLE public.risk_score_history (` (present in the migrated schema, missing from the tampered snapshot), the `FAIL: schema drift...` guidance mentioning `make migrate-snapshot`, and `exit=1`.

- [ ] **Step 3: Missing snapshot — expect exit 1 with regeneration hint**

```bash
PAD=/tmp/claude-1000/-home-rdhagan92-chiliAI/01429c3d-7b34-4c3f-bbcb-fbc0c854ce6b/scratchpad
cd /home/rdhagan92/chiliAI
SNAPSHOT_PATH="$PAD/does_not_exist.sql" scripts/ci_migration_check.sh; echo "exit=$?"
```
Expected: `FAIL: snapshot .../does_not_exist.sql does not exist.` + `Generate it with: scripts/ci_migration_check.sh --update-snapshot`, `exit=1`.

- [ ] **Step 4: Confirm the dev database was never touched**

```bash
docker compose -f /home/rdhagan92/chiliAI/docker-compose.dev.yaml exec -T postgres \
  psql -U chili -d postgres -Atc \
  "SELECT datname FROM pg_database WHERE datname LIKE 'chili%' ORDER BY datname"
```
Expected: `chili` present, `chili_migration_check` absent (the EXIT trap dropped it). No commit in this task — it is pure verification.

---

### Task 4: `make migrate-check` / `make migrate-snapshot`

**Files:**
- Modify: `Makefile` (insert after the `migrate:` target, currently lines 43–44)

**Interfaces:**
- Consumes: `scripts/ci_migration_check.sh` (Task 1).
- Produces: `make migrate-check` (check mode, AC-2) and `make migrate-snapshot` (snapshot refresh — the command Task 7 and every future migration PR runs).

- [ ] **Step 1: Confirm targets don't exist yet**

```bash
cd /home/rdhagan92/chiliAI && make migrate-check 2>&1 | head -1
```
Expected: `make: *** No rule to make target 'migrate-check'.  Stop.`

- [ ] **Step 2: Add the targets**

In `/home/rdhagan92/chiliAI/Makefile`, directly below the existing block
```make
migrate: ## Run database migrations inside the API container
	$(COMPOSE_DEV) exec api alembic upgrade head
```
insert:
```make
# BL-042 / database.04: replay all migrations on a scratch database
# (chili_migration_check) on the compose postgres service and diff the schema
# against backend/database/migrations/snapshots/head.sql. Never touches the
# dev 'chili' database. Regenerate the snapshot in every migration PR.
.PHONY: migrate-check migrate-snapshot
migrate-check: ## Replay migrations on a scratch TimescaleDB and diff schema vs committed snapshot
	scripts/ci_migration_check.sh

migrate-snapshot: ## Regenerate backend/database/migrations/snapshots/head.sql (run after adding a migration)
	scripts/ci_migration_check.sh --update-snapshot
```
(The repo already uses per-block `.PHONY` lines for `demo-tn-subset` and `seed-housing` — follow that pattern; the recipe lines must be TAB-indented.)

- [ ] **Step 3: Verify help listing and a green run**

```bash
cd /home/rdhagan92/chiliAI
make help | grep migrate
make migrate-check; echo "exit=$?"
```
Expected: `make help` lists `migrate`, `migrate-check`, and `migrate-snapshot` with their `##` descriptions; `make migrate-check` ends `OK: migration replay clean; schema matches ...`, `exit=0`.

- [ ] **Step 4: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add Makefile
git commit -m "feat(database): add make migrate-check / migrate-snapshot targets (BL-042)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: CI job `migrations`

**Files:**
- Modify: `.github/workflows/ci.yml` (append a new job after the `backlog` job, i.e. at end of file; **no existing job line changes**)

**Interfaces:**
- Consumes: `scripts/ci_migration_check.sh` (Task 1), committed `head.sql` (Task 2), backend `[postgres]` extra (`backend/pyproject.toml:71-75`).
- Produces: independent CI job `migrations` ("Migrations (replay + snapshot drift)") on the same triggers as the whole workflow (push to prod/main, all PRs, manual dispatch, nightly cron — the workflow-level `on:` block is untouched).

- [ ] **Step 1: Append the job**

At the end of `/home/rdhagan92/chiliAI/.github/workflows/ci.yml` (after the `backlog` job's last line, `pytest tests/scripts/test_backlog_consistency.py --cov=scripts.backlog_consistency --cov-fail-under=85`), append:

```yaml

  migrations:
    name: Migrations (replay + snapshot drift)
    runs-on: ubuntu-latest
    # BL-042 / database.04 (workflow plumbing: _cicd.12). Independent of the
    # backend job: no `needs`, so a schema-drift failure is reported even when
    # unrelated backend tests are red, and existing jobs stay untouched.
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Alembic via the backend postgres extra
        # Only alembic + psycopg are needed; the [postgres] extra pins them to
        # the same versions the backend job resolves.
        run: |
          python -m pip install --upgrade pip
          pip install -e "backend[postgres]"

      - name: Run migration replay + snapshot drift gate
        # The script brings up only the compose postgres service itself (the
        # same service-container pattern as the backend job's alembic step)
        # and works in a scratch database, never the seeded `chili` one.
        run: scripts/ci_migration_check.sh

      - name: Tear down the service stack
        if: always()
        run: docker compose -f docker-compose.dev.yaml down -v
```

- [ ] **Step 2: Verify the YAML parses and existing jobs are untouched**

```bash
cd /home/rdhagan92/chiliAI
backend/.venv/bin/python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print(sorted(d['jobs']))
assert sorted(d['jobs']) == ['api-contracts', 'backend', 'backlog', 'frontend', 'migrations']
print('yaml OK')
"
git diff .github/workflows/ci.yml | grep -c '^-[^-]'; echo "removed-lines(count above) must be 0"
```
Expected: `['api-contracts', 'backend', 'backlog', 'frontend', 'migrations']`, `yaml OK`, and `0` removed lines (append-only change).

- [ ] **Step 3: Note the deferred verification**

Actually pushing and watching the `migrations` job run green on GitHub happens in the **MAIN session at sprint verification** (per Global Constraints) — do not push from this task. Local equivalence was already proven by `make migrate-check` (Task 4 Step 3), which runs the identical script the job runs.

- [ ] **Step 4: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add .github/workflows/ci.yml
git commit -m "ci: add migrations replay + snapshot drift job (BL-042, _cicd.12 plumbing)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation

**Files:**
- Modify: `backend/database/README.md` (add a section after `## Commands`, currently ending line ~48)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–5.
- Produces: the documented standing rule that every migration PR runs `make migrate-snapshot` — this is what makes the 0009/BL-041 sequencing safe even if 0009 lands after this story.

- [ ] **Step 1: Add the gate section to `backend/database/README.md`**

Insert after the existing `## Commands` code block and before `## Configuration`:

````markdown
## Migration drift / replay gate (database.04 / BL-042)

`scripts/ci_migration_check.sh` (repo root) gates every schema-touching PR
(CI job **Migrations (replay + snapshot drift)**; local parity via
`make migrate-check`). Each run:

1. brings up only the compose `postgres` service and force-recreates a
   **scratch** database `chili_migration_check` — the dev `chili` database is
   never touched, and `DATABASE_URL` is scoped per command, never exported;
2. replays the full history on the fresh database: `alembic upgrade head` →
   `alembic downgrade base` (failing if any `public` table is left behind —
   every migration must implement a complete `downgrade()`) →
   `alembic upgrade head`;
3. dumps the resulting schema with in-container `pg_dump --schema-only`
   (normalized: version-comment headers, psql `\restrict` tokens, and the
   `SET`/`set_config` preamble stripped; TimescaleDB hypertable registrations
   appended as a deterministic footer) and diffs it against the committed
   snapshot `backend/database/migrations/snapshots/head.sql`, failing loudly
   with a unified diff on drift.

```bash
make migrate-check     # local parity with the CI job (exit 1 + diff on drift)
make migrate-snapshot  # regenerate snapshots/head.sql (idempotent, re-runnable)
```

**Every PR that adds or edits a migration must run `make migrate-snapshot`
and commit the refreshed `snapshots/head.sql`**, otherwise the CI gate fails
with a diff — that failure is the gate working as designed. Never regenerate
the snapshot just to silence a drift you did not intend. The snapshot is
content-based (`alembic_version` is excluded, so no revision IDs appear in
it); renumbering revision files does not invalidate it.
````

- [ ] **Step 2: Consistency sweep of the other instruction/docs surfaces**

Per CLAUDE.md, check (read; update only if they now contradict reality):
```bash
grep -rn "migrate-check\|ci_migration_check\|migration drift\|snapshots/head" \
  /home/rdhagan92/chiliAI/CLAUDE.md \
  /home/rdhagan92/chiliAI/README.md \
  /home/rdhagan92/chiliAI/docs/architecture.md \
  /home/rdhagan92/chiliAI/.github/copilot-instructions.md \
  /home/rdhagan92/chiliAI/.github/instructions/ 2>/dev/null
```
Expected: no stale contradictions (these files do not currently claim anything about migration gating). If `docs/architecture.md` or the root `README.md` has a CI-gates or database section that enumerates jobs/commands, add one line mirroring the README section above; otherwise leave them unchanged. Do **not** edit `docs/backlog/database.md` status or the database.08–.13 revision-ID text — story status flips are handled at sprint verification in the main session, and the docs-collision carryover is explicitly out of scope (AC-5).

- [ ] **Step 3: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/database/README.md docs/architecture.md README.md
git commit -m "docs(database): document migration drift/replay gate and snapshot refresh rule (BL-042)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Snapshot refresh after migration 0009 (BL-041 sequencing)

**Files:**
- Modify (regenerated): `backend/database/migrations/snapshots/head.sql` — **only if 0009 exists**.

**Interfaces:**
- Consumes: `make migrate-snapshot` (Task 4); BL-041's migration `backend/database/migrations/versions/0009_*.py` (owned by BL-041, not this plan).

Migration 0009 did not exist when this plan was written. This task is the sprint-sequencing hook from AC-4: run it **after BL-041's migration lands on this branch** and before sprint verification. If BL-041 merges via its own PR instead, that PR must run the same two commands (the rule Task 6 documented) — the gate turning red on an unrefreshed 0009 is correct behavior, and the fix is always the same re-runnable command.

- [ ] **Step 1: Check whether 0009 has landed**

```bash
ls /home/rdhagan92/chiliAI/backend/database/migrations/versions/ | grep '^0009' || echo "0009 not landed - task deferred"
```
If `0009 not landed - task deferred`: stop here; record in the task tracker that Task 7 re-runs when BL-041 lands. Nothing else to do — Tasks 1–6 are complete and green at head 0008.

- [ ] **Step 2: Regenerate and inspect the snapshot**

```bash
cd /home/rdhagan92/chiliAI
make migrate-snapshot
git diff --stat backend/database/migrations/snapshots/head.sql
git diff backend/database/migrations/snapshots/head.sql | grep '^+CREATE TABLE'
```
Expected: the diff adds exactly the DDL 0009 introduces (BL-041's `SourceDocumentStatusStore` table, e.g. a `+CREATE TABLE public.source_document_status (`-style line plus its indexes) and removes nothing. If anything unrelated changed, stop and investigate — that would be real drift in an existing migration.

- [ ] **Step 3: Verify check mode is green at the new head, then commit**

```bash
cd /home/rdhagan92/chiliAI
make migrate-check; echo "exit=$?"
git add backend/database/migrations/snapshots/head.sql
git commit -m "chore(database): refresh schema snapshot after migration 0009 (BL-042/BL-041)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
Expected: `OK: migration replay clean; schema matches ...`, `exit=0`, then a clean commit.

---

## Acceptance-Criteria Traceability

| AC | Where satisfied |
|---|---|
| 1. Script: fresh TimescaleDB, upgrade→downgrade→upgrade + snapshot drift check | Task 1 (script), Task 2 (snapshot), Task 3 (clean/drift/missing-snapshot exit codes proven live) |
| 2. `make migrate-check` local parity | Task 4 |
| 3. CI job reusing the service-container pattern | Task 5 (compose `up -d --wait postgres` inside the script, same as ci.yml:71; teardown `down -v` `if: always()` like ci.yml:134-137; push verification deferred to main session) |
| 4. Same-sprint sequencing with 0009 | `--update-snapshot` is re-runnable (Task 2 Step 4 proves determinism); Task 6 documents the standing refresh rule; Task 7 is the guarded refresh |
| 5. No worsening of database.08–.13 revision-ID collision | Snapshot excludes `alembic_version` (Task 2 Step 3 asserts zero revision-ID mentions); no revision files renamed; backlog docs untouched (Task 6 Step 2) |

## Overlap Note (why no new pytest)

`backend/tests/database/test_migrations.py` already covers downgrade-base/upgrade-head semantics as integration pytest against `DATABASE_URL`. This gate deliberately adds what pytest cannot give cheaply — a *fresh* database per run and a committed-snapshot diff — as a standalone script, so no pytest duplicate is created; the script's behavior (exit 0 clean / exit 1 drift with diff / exit 2 guard) is exercised live in Tasks 1 and 3 instead.
