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
# -E (errtrace) so the ERR trap below also fires for failures inside function
# bodies (admin_psql/scratch_psql/alembic_cmd) -- without it bash does not
# inherit ERR traps into functions and mid-run tool failures would leak the
# tool's own exit code instead of the documented exit 1.
set -Eeuo pipefail

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

# Past this point all usage/environment guards (exit 2) are behind us: any
# tool failure that reaches here (psql, alembic, docker compose, pg_dump)
# is a replay/check failure, not a usage error, and must map to exit 1 per
# the documented exit-code contract. Explicit `exit 1`/`exit 2` calls below
# are unaffected -- bash does not run the ERR trap for an explicit `exit`.
trap 'echo "ERROR: migration replay/check step failed (see output above)." >&2; exit 1' ERR

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
