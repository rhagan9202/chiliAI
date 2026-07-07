"""Seed the Air Force housing demo through the real API.

Drives a running chiliAI API (host uvicorn or the `make dev` stack) with real
HTTP calls — nothing is mocked or written behind the API's back:

1. ``POST /knowledgebases`` creates a fresh KB stamped with the active
   domain (run the API with the ``department_air_force_housing`` pack).
2. ``POST /records/{kb}/files`` uploads every housing feed fixture CSV from
   ``docs/testing/knowledge_base_fixtures/air_force_housing/`` through the
   structured-ingestion endpoint (validation, idempotency, and workflow
   events all engage exactly as they would for an operator upload).
3. Optionally (``--scorecards``) generates scorecard runs for each configured
   template against a sample of installations via ``POST /scorecards/runs``.

The fixture CSVs live under ``docs/`` (not mounted into the API container),
so run this from the repo host: the data still flows through the container's
real ingestion path over HTTP.

Always seeds a FRESH knowledge base. Record ingestion is insert-only (rows
are keyed by record id and re-uploads of changed values silently no-op), so
re-seeding corrected fixtures into an existing KB would leave stale data in
place. The script therefore refuses to run when a KB with the target name
already exists — pass a new ``--kb-name`` or delete the old KB first.

Usage — containerized stack (worker completes ingest workflows):

    make dev-domain DOMAIN=department_air_force_housing
    make seed-housing            # wraps: backend/.venv/bin/python -m tools.seed_housing_demo
    make seed-housing SEED_ARGS="--scorecards"

Usage — bare host API (no worker; note ``CHILI_ENV`` is required or the app
refuses to boot):

    cd backend && CHILI_ENV=local \
      CHILI_CONFIG_PATH=$PWD/config/defaults/department_air_force_housing.yaml \
      .venv/bin/uvicorn api.app:create_app --factory --port 8000
    PYTHONPATH=backend backend/.venv/bin/python -m tools.seed_housing_demo --no-worker
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "docs" / "testing" / "knowledge_base_fixtures" / "air_force_housing"

# feed name (pack records.feeds) -> fixture file. Feeds missing from the
# active pack are reported and skipped so the seed degrades loudly, not badly.
FEED_FILES: dict[str, str] = {
    "umd_authorizations": "umd_sample.csv",
    "bah_rates": "bah_sample.csv",
    "housing_inventory": "inventory_sample.csv",
    "market_availability": "market_sample.csv",
    "area_demographics": "demographics_sample.csv",
    "resident_experience": "resident_experience_sample.csv",
}


@dataclass(frozen=True)
class SeedResult:
    """What the seed run produced, for the closing summary."""

    knowledge_base_id: str
    feeds_loaded: list[str]
    feeds_skipped: list[str]
    rows_accepted: int
    scorecard_runs: int


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="Base URL of the running chiliAI API.",
    )
    parser.add_argument(
        "--kb-name",
        default="Air Force Housing Demo",
        help=(
            "Display name for the freshly created knowledge base. Seeding "
            "refuses to reuse an existing KB of the same name: records are "
            "insert-only, so re-uploads into an old KB silently keep stale "
            "rows."
        ),
    )
    parser.add_argument(
        "--scorecards",
        action="store_true",
        help="Also generate scorecard runs for each template and installation.",
    )
    parser.add_argument(
        "--scorecard-installations",
        type=int,
        default=0,
        metavar="N",
        help=(
            "With --scorecards, limit run generation to the first N "
            "installations (0 = all)."
        ),
    )
    parser.add_argument(
        "--no-worker",
        action="store_true",
        help=(
            "Target a worker-less stack (bare uvicorn): cancel each upload's "
            "tracked workflow run via POST /workflows/{id}/cancel instead of "
            "waiting for the worker to complete it. Record data is unaffected "
            "(rows persist before the run starts)."
        ),
    )
    parser.add_argument(
        "--workflow-timeout",
        type=float,
        default=90.0,
        metavar="SECONDS",
        help="How long to wait for each ingest workflow to finish.",
    )
    return parser.parse_args(argv)


def _await_kb_idle(
    client: httpx.Client,
    kb_id: str,
    *,
    cancel_stalled: bool,
    timeout_seconds: float,
) -> None:
    """Wait until the KB has no queued/running workflow (uploads 409 otherwise).

    With a worker attached each records run completes in moments. In
    ``--no-worker`` mode the tracked run can never complete, so it is
    cancelled through the supported cancel endpoint instead.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        active: list[dict[str, object]] = []
        for run_status in ("queued", "running"):
            response = client.get(
                "/workflows",
                params={
                    "knowledge_base_id": kb_id,
                    "status": run_status,
                    "limit": 50,
                },
            )
            response.raise_for_status()
            active.extend(response.json()["items"])
        if not active:
            return
        if cancel_stalled:
            for run in active:
                cancel = client.post(f"/workflows/{run['id']}/cancel")
                cancel.raise_for_status()
            continue
        if time.monotonic() > deadline:
            raise SystemExit(
                f"Workflow run(s) for KB {kb_id} still active after "
                f"{timeout_seconds:.0f}s — is the chili-worker running? "
                "(pass --no-worker when seeding a bare uvicorn stack)"
            )
        time.sleep(1.0)


def _quarter_bounds(snapshot: date) -> tuple[date, date]:
    quarter_start_month = 3 * ((snapshot.month - 1) // 3) + 1
    return snapshot.replace(month=quarter_start_month, day=1), snapshot


def _fixture_installations() -> list[str]:
    with (FIXTURES / "umd_sample.csv").open() as handle:
        return [row["installation_id"] for row in csv.DictReader(handle)]


def _fixture_snapshot_date() -> date:
    with (FIXTURES / "umd_sample.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    return date.fromisoformat(rows[0]["snapshot_date"])


def _refuse_existing_kb(client: httpx.Client, name: str) -> None:
    """Refuse to seed when a same-named KB already exists.

    ``raw_records`` persistence is insert-only (conflict on record id is a
    no-op), so uploading corrected fixture rows into an existing KB silently
    keeps the old values — and a scorecard re-run would grade stale data.
    Seeding must always target a fresh KB.
    """
    offset = 0
    while True:
        response = client.get(
            "/knowledgebases", params={"limit": 500, "offset": offset}
        )
        response.raise_for_status()
        body = response.json()
        for item in body["items"]:
            if item["name"] == name:
                raise SystemExit(
                    f"A knowledge base named '{name}' already exists "
                    f"({item['id']}). Records are insert-only, so re-seeding "
                    "into it would silently keep stale rows. Pass a new "
                    "--kb-name (or delete the old knowledge base) and re-run."
                )
        offset += len(body["items"])
        if offset >= int(body["total"]) or not body["items"]:
            return


def _create_knowledge_base(client: httpx.Client, name: str) -> str:
    _refuse_existing_kb(client, name)
    response = client.post(
        "/knowledgebases",
        json={"name": name, "description": "Seeded Air Force housing demo data."},
    )
    response.raise_for_status()
    kb_id = str(response.json()["id"])
    print(f"created knowledge base {kb_id} ({name})")
    return kb_id


def _upload_feeds(
    client: httpx.Client,
    kb_id: str,
    *,
    cancel_stalled: bool,
    timeout_seconds: float,
) -> tuple[list[str], list[str], int]:
    loaded: list[str] = []
    skipped: list[str] = []
    accepted = 0
    for feed_name, filename in FEED_FILES.items():
        path = FIXTURES / filename
        if not path.is_file():
            print(f"  SKIP {feed_name}: fixture {filename} not found")
            skipped.append(feed_name)
            continue
        _await_kb_idle(
            client,
            kb_id,
            cancel_stalled=cancel_stalled,
            timeout_seconds=timeout_seconds,
        )
        response = client.post(
            f"/records/{kb_id}/files",
            data={"feed": feed_name},
            files={"file": (filename, path.read_bytes(), "text/csv")},
        )
        if response.status_code == 404 and feed_name in response.text:
            print(f"  SKIP {feed_name}: feed not declared in the active pack")
            skipped.append(feed_name)
            continue
        response.raise_for_status()
        receipt = response.json()
        accepted += int(receipt["accepted_count"])
        rejected = int(receipt["rejected_count"])
        print(
            f"  {feed_name}: accepted={receipt['accepted_count']} "
            f"rejected={rejected} duplicate={receipt['duplicate']}"
        )
        if rejected:
            for item in receipt["rejected"][:5]:
                print(f"    rejected row {item['index']}: {item['reason']}")
            raise SystemExit(f"Feed '{feed_name}' rejected {rejected} rows; aborting.")
        loaded.append(feed_name)
    return loaded, skipped, accepted


def _generate_scorecards(
    client: httpx.Client, kb_id: str, *, limit: int
) -> int:
    templates_response = client.get("/scorecards/templates")
    templates_response.raise_for_status()
    templates = templates_response.json()["items"]
    installations = _fixture_installations()
    if limit > 0:
        installations = installations[:limit]
    period_start, period_end = _quarter_bounds(_fixture_snapshot_date())

    generated = 0
    for template in templates:
        for installation_id in installations:
            response = client.post(
                "/scorecards/runs",
                json={
                    "knowledge_base_id": kb_id,
                    "template_id": template["id"],
                    "scope_type": "installation",
                    "scope_id": installation_id,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
            )
            response.raise_for_status()
            generated += 1
        print(f"  {template['id']}: generated {len(installations)} runs")
    return generated


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if not FIXTURES.is_dir():
        print(f"Fixture directory not found: {FIXTURES}", file=sys.stderr)
        return 1

    with httpx.Client(base_url=args.api, timeout=60.0) as client:
        kb_id = _create_knowledge_base(client, args.kb_name)
        print("uploading feed fixtures:")
        loaded, skipped, accepted = _upload_feeds(
            client,
            kb_id,
            cancel_stalled=args.no_worker,
            timeout_seconds=args.workflow_timeout,
        )
        _await_kb_idle(
            client,
            kb_id,
            cancel_stalled=args.no_worker,
            timeout_seconds=args.workflow_timeout,
        )
        runs = 0
        if args.scorecards:
            print("generating scorecard runs:")
            runs = _generate_scorecards(
                client, kb_id, limit=args.scorecard_installations
            )

    result = SeedResult(
        knowledge_base_id=kb_id,
        feeds_loaded=loaded,
        feeds_skipped=skipped,
        rows_accepted=accepted,
        scorecard_runs=runs,
    )
    print(
        f"\nseed complete: kb={result.knowledge_base_id} "
        f"feeds={len(result.feeds_loaded)} loaded"
        f" ({', '.join(result.feeds_skipped) or 'none'} skipped)"
        f" rows={result.rows_accepted} scorecard_runs={result.scorecard_runs}"
    )
    print(
        "open the dashboard: http://localhost:5173/housing "
        f"(API: {args.api}/housing/overview)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
