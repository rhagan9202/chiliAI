/**
 * Playwright global setup for full-stack e2e.
 *
 * Seeds a deterministic scenario into the REAL backend stores by calling the
 * dev-gated POST /admin/dev-seed endpoint (registered only when
 * CHILI_ENV != production), then writes the returned ids to e2e/.seeded.json
 * for specs to read via e2e/helpers/seeded.ts.
 *
 * Requires the full stack to be running (make test-e2e brings it up first; for
 * local runs, start `make dev` separately). No API mocking — the UI under test
 * talks to the real API/worker/services.
 */

import { writeFileSync } from 'node:fs'

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

async function globalSetup(): Promise<void> {
  await waitForApi()

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
