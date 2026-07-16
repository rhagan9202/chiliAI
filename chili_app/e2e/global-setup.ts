/**
 * Playwright global setup for full-stack e2e.
 *
 * Seeds a deterministic scenario into the REAL backend stores by calling the
 * dev-gated POST /admin/dev-seed endpoint (registered only when
 * CHILI_ENV != production), then writes the returned ids to e2e/.seeded.json
 * for specs to read via e2e/helpers/seeded.ts. Seeding only happens when the
 * stack's active domain is the medicare pack: on any other pack (probed via
 * GET /config/domain) dev-seed is skipped automatically so the seeded KB
 * cannot win newest-KB resolution over the pack's own demo KB.
 *
 * Before seeding anything it snapshots the knowledge bases that already exist
 * on the stack to e2e/.kb-baseline.json. global-teardown.ts deletes every KB
 * created after that baseline (dev-seed KBs, spec-created warn-e2e KBs, ...)
 * so an e2e run can never leave a fresh, feed-empty KB squatting on the
 * newest-ready KB resolution that the /housing endpoints and dashboards use —
 * a leaked e2e KB silently degrades a seeded demo stack to an empty view.
 *
 * Requires the full stack to be running (make test-e2e brings it up first; for
 * local runs, start `make dev` separately). No API mocking — the UI under test
 * talks to the real API/worker/services.
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs'

import { KB_BASELINE_PATH, deleteKbsNotInBaseline, type KbBaseline } from './helpers/kbBaseline'
import type { SeededIds } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'
const SEEDED_PATH = 'e2e/.seeded.json'

async function waitForApi(attempts = 90): Promise<void> {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`${API}/health`)
      if (res.ok) return
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error(`API at ${API} did not become healthy. Is the stack running (make dev)?`)
}

/**
 * A baseline file at setup time means the previous run never reached
 * global-teardown (crash, Ctrl-C, system hang): its KBs are still on the
 * stack. Reclaim them against the STALE baseline before snapshotting anew —
 * otherwise the fresh snapshot would adopt the leaked KBs as "pre-existing"
 * and no future run would ever clean them up.
 */
async function reclaimStaleBaseline(): Promise<void> {
  if (!existsSync(KB_BASELINE_PATH)) return
  const stale = JSON.parse(readFileSync(KB_BASELINE_PATH, 'utf-8')) as KbBaseline
  console.warn(
    `[e2e] stale ${KB_BASELINE_PATH} from ${stale.captured_at} — previous run was interrupted; reclaiming its leaked KBs`,
  )
  const result = await deleteKbsNotInBaseline(API, stale, '[e2e] stale-baseline reclaim:')
  if (result.failed > 0) {
    throw new Error(
      `[e2e] stale-baseline reclaim left ${result.failed} leaked KB(s) behind — delete them manually before running e2e.`,
    )
  }
  console.log(`[e2e] stale-baseline reclaim: ${result.deleted} leaked KB(s) deleted`)
}

async function snapshotKnowledgeBases(): Promise<void> {
  const res = await fetch(`${API}/knowledgebases`)
  if (!res.ok) {
    throw new Error(`GET /knowledgebases failed (${res.status}): ${await res.text()}`)
  }
  const payload = (await res.json()) as { items: { id: string }[] }
  const baseline: KbBaseline = {
    captured_at: new Date().toISOString(),
    knowledge_base_ids: payload.items.map((item) => item.id),
  }
  writeFileSync(KB_BASELINE_PATH, JSON.stringify(baseline, null, 2))
  console.log(
    `[e2e] KB baseline -> ${KB_BASELINE_PATH}: ${baseline.knowledge_base_ids.length} pre-existing KBs (teardown deletes anything newer)`,
  )
}

/** The domain the dev-seed scenario's asserted display values belong to. */
const DEV_SEED_DOMAIN = 'medicare_fraud'

async function fetchActiveDomainName(): Promise<string> {
  const res = await fetch(`${API}/config/domain`)
  if (!res.ok) {
    throw new Error(`GET /config/domain failed (${res.status}): ${await res.text()}`)
  }
  const payload = (await res.json()) as { domain: { name: string } }
  return payload.domain.name
}

async function globalSetup(): Promise<void> {
  await waitForApi()

  // Reclaim any KBs leaked by a previous interrupted run BEFORE snapshotting,
  // then snapshot BEFORE any seeding so the dev-seed KB itself is torn down too.
  await reclaimStaleBaseline()
  await snapshotKnowledgeBases()

  // E2E_SKIP_DEV_SEED=1 skips the /admin/dev-seed scenario. Use it ONLY when
  // running specs that do not read e2e/.seeded.json (e.g. the housing spec
  // against an already-seeded housing-pack stack, where dev-seed would create
  // a newer empty KB and flip the /housing endpoints off the seeded demo KB).
  if (process.env['E2E_SKIP_DEV_SEED'] === '1') {
    console.log('[e2e] E2E_SKIP_DEV_SEED=1 — skipping /admin/dev-seed; seeded-id specs will fail')
    return
  }

  // Domain guard: dev-seed's asserted display values belong to the medicare
  // pack, and on any other pack the seeded KB would become the newest
  // ready/active KB — flipping the /housing endpoints (and every
  // newest-KB-resolving dashboard) off the pack's seeded demo KB for the
  // whole run. Skip automatically on non-medicare stacks; E2E_SKIP_DEV_SEED=1
  // above remains the explicit override for medicare stacks.
  const activeDomain = await fetchActiveDomainName()
  if (activeDomain !== DEV_SEED_DOMAIN) {
    console.log(
      `[e2e] active domain "${activeDomain}" != "${DEV_SEED_DOMAIN}" — skipping /admin/dev-seed ` +
        '(the medicare scenario would squat on newest-KB resolution and poison the demo stack); ' +
        'seeded-id specs will fail; domain-adaptive specs run in live mode. ' +
        'E2E_SKIP_DEV_SEED=1 is no longer required here — it stays as the explicit override.',
    )
    return
  }

  const res = await fetch(`${API}/admin/dev-seed`, { method: 'POST' })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `POST /admin/dev-seed failed (${res.status}): ${body}. ` +
        `The endpoint is dev-only — ensure CHILI_ENV != production.`,
    )
  }
  const ids = (await res.json()) as SeededIds
  writeFileSync(SEEDED_PATH, JSON.stringify(ids, null, 2))
  console.log(`[e2e] seeded scenario -> ${SEEDED_PATH}: kb=${ids.knowledge_base_id}`)
}

export default globalSetup
