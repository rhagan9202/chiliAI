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

import { KB_BASELINE_PATH, type KbBaseline } from './helpers/kbBaseline'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

async function globalTeardown(): Promise<void> {
  if (!existsSync(KB_BASELINE_PATH)) {
    console.warn(`[e2e] no ${KB_BASELINE_PATH} — skipping KB teardown (setup did not run?)`)
    return
  }
  const baseline = JSON.parse(readFileSync(KB_BASELINE_PATH, 'utf-8')) as KbBaseline
  const preExisting = new Set(baseline.knowledge_base_ids)

  const res = await fetch(`${API}/knowledgebases`)
  if (!res.ok) {
    console.warn(`[e2e] GET /knowledgebases failed (${res.status}) — skipping KB teardown`)
    return
  }
  const payload = (await res.json()) as { items: { id: string; name: string }[] }
  const created = payload.items.filter((kb) => !preExisting.has(kb.id))

  let failures = 0
  for (const kb of created) {
    const del = await fetch(`${API}/knowledgebases/${encodeURIComponent(kb.id)}`, {
      method: 'DELETE',
    })
    if (del.ok) {
      console.log(`[e2e] teardown deleted KB "${kb.name}" (${kb.id})`)
    } else {
      failures += 1
      console.error(
        `[e2e] teardown FAILED to delete KB "${kb.name}" (${kb.id}): ${del.status} ${await del
          .text()
          .catch(() => '')}`,
      )
    }
  }
  console.log(
    `[e2e] KB teardown: ${created.length - failures}/${created.length} run-created KBs deleted, ${preExisting.size} pre-existing KBs untouched`,
  )
  if (failures === 0) {
    rmSync(KB_BASELINE_PATH, { force: true })
  } else {
    throw new Error(
      `[e2e] KB teardown left ${failures} run-created KB(s) behind — delete them manually before demoing (they poison newest-ready KB resolution).`,
    )
  }
}

export default globalTeardown
