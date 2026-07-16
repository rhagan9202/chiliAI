/**
 * Playwright global teardown for full-stack e2e.
 *
 * Deletes every knowledge base the e2e run created — anything present now
 * that was not in the e2e/.kb-baseline.json snapshot taken by global-setup
 * before seeding. This covers the /admin/dev-seed KB and every spec-created
 * KB (warn-e2e uploads, domain-mismatch KBs, ...). Deletion goes through the
 * real DELETE /knowledgebases/{id} endpoint, so the backend's cleanup cascade
 * (documents, records, observations, scorecard runs, workflows) applies.
 *
 * Why this matters: the /housing endpoints and the dashboards resolve the
 * NEWEST ready/active KB of the active domain. A leaked e2e KB is newer and
 * feed-empty, so without teardown a verification run silently degrades a
 * seeded demo stack to an empty view.
 *
 * Pre-existing KBs (the seeded demo KB included) are never touched.
 */

import { existsSync, readFileSync, rmSync } from 'node:fs'

import { KB_BASELINE_PATH, deleteKbsNotInBaseline, type KbBaseline } from './helpers/kbBaseline'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

async function globalTeardown(): Promise<void> {
  if (!existsSync(KB_BASELINE_PATH)) {
    console.warn(`[e2e] no ${KB_BASELINE_PATH} — skipping KB teardown (setup did not run?)`)
    return
  }
  const baseline = JSON.parse(readFileSync(KB_BASELINE_PATH, 'utf-8')) as KbBaseline

  const result = await deleteKbsNotInBaseline(API, baseline, '[e2e] teardown')
  if (!result.listed) {
    // Listing failed — nothing was deleted. Keep the baseline on disk so the
    // next run's stale-baseline reclaim (global-setup) can retry.
    console.warn(`[e2e] KB teardown skipped (listing failed) — ${KB_BASELINE_PATH} kept for reclaim`)
    return
  }
  console.log(
    `[e2e] KB teardown: ${result.deleted}/${result.deleted + result.failed} run-created KBs deleted, ${baseline.knowledge_base_ids.length} pre-existing KBs untouched`,
  )
  if (result.failed === 0) {
    rmSync(KB_BASELINE_PATH, { force: true })
  } else {
    // Baseline stays on disk after a FAILED teardown so the next run's
    // stale-baseline reclaim (global-setup) can retry these deletions.
    throw new Error(
      `[e2e] KB teardown left ${result.failed} run-created KB(s) behind — delete them manually before demoing (they poison newest-ready KB resolution).`,
    )
  }
}

export default globalTeardown
