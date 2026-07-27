/**
 * Domain-pack switching for specs whose page is owned by a non-default pack.
 *
 * Since UXA-103 the SPA refuses routes the active pack does not declare, so a
 * spec that drives `/housing` has to run under the housing pack rather than
 * relying on the shared medicare stack rendering it anyway. Reference mode is a
 * property of the *data* (no housing rows ingested), not of the pack, so
 * swapping the pack keeps those specs in reference mode — it only makes the
 * route reachable.
 *
 * The stack is shared and specs run serially (`workers: 1`), so every caller
 * must restore the original pack in `afterAll` or the rest of the suite runs
 * under the wrong domain.
 */
import { expect, request as playwrightRequest } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

interface PackSummary {
  path: string
  domain_name: string
}

interface PackListResponse {
  packs: PackSummary[]
  active: { config_path?: string | null }
}

export async function switchPack(request: APIRequestContext, pack: string): Promise<void> {
  const res = await request.post(`${API}/config/switch`, { data: { pack } })
  expect(
    res.ok(),
    `POST /config/switch to '${pack}' must succeed (needs CHILI_DEV_ANONYMOUS_ROLE=admin)`,
  ).toBeTruthy()
}

/**
 * Switch to the pack owning `domainName`. Returns a restore function that puts
 * the original pack back, or null when the stack is already on that pack (in
 * which case nothing needs restoring).
 */
export async function useDomainPack(domainName: string): Promise<(() => Promise<void>) | null> {
  const request = await playwrightRequest.newContext()
  try {
    const domainRes = await request.get(`${API}/config/domain`)
    expect(domainRes.ok(), 'GET /config/domain must succeed').toBeTruthy()
    const active = (await domainRes.json()) as { domain: { name: string } }
    if (active.domain.name === domainName) {
      return null
    }

    const packsRes = await request.get(`${API}/config/packs`)
    expect(
      packsRes.ok(),
      'GET /config/packs must succeed — run the stack with CHILI_DEV_ANONYMOUS_ROLE=admin',
    ).toBeTruthy()
    const packList = (await packsRes.json()) as PackListResponse

    const target = packList.packs.find((pack) => pack.domain_name === domainName)
    expect(target, `a pack for domain '${domainName}' must be installed`).toBeTruthy()
    const originalRef =
      packList.active.config_path ??
      packList.packs.find((pack) => pack.domain_name === active.domain.name)?.path
    expect(originalRef, 'the active pack must be resolvable so it can be restored').toBeTruthy()

    await switchPack(request, target!.path)

    return async () => {
      const restoreRequest = await playwrightRequest.newContext()
      try {
        await switchPack(restoreRequest, originalRef!)
      } finally {
        await restoreRequest.dispose()
      }
    }
  } finally {
    await request.dispose()
  }
}
