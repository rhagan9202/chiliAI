/**
 * Knowledge Bases domain scoping (full stack). The page's knowledge base
 * selector defaults to KBs stamped with the ACTIVE domain (plus legacy KBs
 * without a domain stamp) and offers a show-all-domains toggle whenever other
 * domains' KBs are hidden.
 *
 * The suite is domain-adaptive: it reads GET /config/domain and
 * GET /knowledgebases from the real API, computes the expected scoped set with
 * the same rule the UI uses (a KB is out of scope only when both it and the
 * active config carry a domain name and they differ), and asserts the selector
 * matches — under the housing pack the persisted medicare e2e KBs are hidden,
 * under the medicare pack the persisted housing demo KB is hidden. When no
 * cross-domain KB exists (fresh stack) the toggle must be absent and the full
 * list shown. Read-only against the shared seeded scenario.
 */
import { expect, test } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

type KnowledgeBaseItem = {
  id: string
  name: string
  domain?: string | null
}

let activeDomainName: string
let allKnowledgeBases: KnowledgeBaseItem[]
let scopedKnowledgeBases: KnowledgeBaseItem[]
let hiddenCount: number

function countLabel(count: number): string {
  return `${count} ${count === 1 ? 'knowledge base' : 'knowledge bases'}`
}

test.beforeAll(async () => {
  const configRes = await fetch(`${API}/config/domain`)
  if (!configRes.ok) {
    throw new Error(`GET /config/domain failed (${configRes.status})`)
  }
  const config = (await configRes.json()) as { domain: { name: string } }
  activeDomainName = config.domain.name

  const kbRes = await fetch(`${API}/knowledgebases`)
  if (!kbRes.ok) {
    throw new Error(`GET /knowledgebases failed (${kbRes.status})`)
  }
  allKnowledgeBases = ((await kbRes.json()) as { items: KnowledgeBaseItem[] }).items
  // Mirror of src/components/knowledgebase/domainMismatch.ts: KBs without a
  // domain stamp are legacy and always in scope.
  scopedKnowledgeBases = allKnowledgeBases.filter(
    (kb) => !kb.domain || kb.domain === activeDomainName,
  )
  hiddenCount = allKnowledgeBases.length - scopedKnowledgeBases.length
})

test.describe('Knowledge Bases domain scoping', () => {
  test('defaults to active-domain KBs and reveals all domains via the toggle', async ({
    page,
  }) => {
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

    const listItems = page.locator('.ingestion-kb-list__item')
    const countChip = page.locator('.ingestion-kb-selector__header .ui-chip')
    const toggle = page.getByTestId('kb-show-all-domains-toggle')

    if (hiddenCount === 0) {
      // Single-domain stack: nothing to hide, so no toggle renders and the
      // full list is the scoped list.
      await expect(toggle).toHaveCount(0)
      await expect(countChip).toHaveText(countLabel(allKnowledgeBases.length))
      await expect(listItems).toHaveCount(allKnowledgeBases.length)
      return
    }

    // Default scope: only active-domain (and legacy unstamped) KBs are listed.
    await expect(toggle).toBeVisible()
    await expect(toggle).toHaveText(`Show all domains (${hiddenCount} hidden)`)
    await expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await expect(countChip).toHaveText(countLabel(scopedKnowledgeBases.length))
    if (scopedKnowledgeBases.length > 0) {
      await expect(listItems).toHaveCount(scopedKnowledgeBases.length)
    } else {
      await expect(listItems).toHaveCount(0)
      await expect(page.getByText('No knowledge bases in the active domain')).toBeVisible()
    }

    // Out-of-scope KBs are genuinely absent, not merely de-emphasized. Assert
    // by name using a hidden KB whose name no in-scope KB shares (names are
    // not unique across domains, e.g. recurring "E2E Seed KB" seeds).
    const scopedNames = new Set(scopedKnowledgeBases.map((kb) => kb.name))
    const hiddenKb = allKnowledgeBases.find(
      (kb) => kb.domain && kb.domain !== activeDomainName && !scopedNames.has(kb.name),
    )
    if (hiddenKb) {
      await expect(
        listItems.locator('.ingestion-kb-list__name', { hasText: hiddenKb.name }),
      ).toHaveCount(0)
    }

    // The toggle reveals the full cross-domain list...
    await toggle.click()
    await expect(toggle).toHaveText('Scope to active domain')
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await expect(countChip).toHaveText(countLabel(allKnowledgeBases.length))
    await expect(listItems).toHaveCount(allKnowledgeBases.length)

    // ...and scoping back down restores the active-domain view.
    await toggle.click()
    await expect(toggle).toHaveText(`Show all domains (${hiddenCount} hidden)`)
    await expect(countChip).toHaveText(countLabel(scopedKnowledgeBases.length))
    await expect(listItems).toHaveCount(scopedKnowledgeBases.length)
  })
})
