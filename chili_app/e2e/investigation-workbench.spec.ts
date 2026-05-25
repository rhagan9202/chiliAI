/**
 * Flow 4: Investigation workbench basic load and entity search
 *
 * Verifies that the InvestigationWorkbenchPage renders the search interface
 * and surfaces entity results when the investigation search endpoint responds.
 *
 * Note: The investigation workbench does NOT use a <canvas> element. It renders
 * entity results as list-item buttons and a neighborhood list — all standard DOM.
 *
 * Mocked endpoints (host-anchored):
 *   GET http://localhost:5173/api/auth/me                                → SessionUser
 *   GET http://localhost:5173/api/config/domain                         → DomainConfig
 *   GET http://localhost:5173/api/config/features                       → DomainFeatures
 *   GET http://localhost:5173/api/events/stream                         → SSE stub
 *   GET http://localhost:5173/api/knowledgebases                        → KnowledgeBaseListResponse
 *   GET http://localhost:5173/api/alerts                                → AlertListResponse
 *   GET http://localhost:5173/api/investigation/search?**               → InvestigationEntitySearchResponse
 *
 * Endpoint paths verified against:
 *   - searchInvestigationEntities: src/api/investigation.ts →
 *       apiFetch('/investigation/search?kb_id=...&q=...')
 *   - getAlerts: src/api/alerts.ts → apiFetch('/alerts')
 *   - getKnowledgeBases: src/api/knowledgebases.ts → apiFetch('/knowledgebases')
 *
 * Response shapes verified against:
 *   - InvestigationEntitySearchResponse → src/api/contracts.ts (InvestigationEntitySearchResponse)
 *   - RuntimeEntity → src/api/contracts.ts
 *   - AlertListResponse → src/api/contracts.ts
 *   - KnowledgeBaseListResponse → src/api/contracts.ts
 *
 * Route: /investigation → InvestigationWorkbenchPage (router.tsx)
 */

import { test, expect } from '@playwright/test'

import { mockAuthenticatedShell, mockKnowledgeBases } from './helpers/mocks'

const API = 'http://localhost:5173/api'

/** Minimal KnowledgeBaseSummaryResponse — shape from src/api/contracts.ts */
const FAKE_KB = {
  id: 'kb-001',
  name: 'Medicare FY2024',
  description: 'Test KB',
  status: 'ready' as const,
  document_count: 5,
  entity_count: 100,
  relationship_count: 200,
  created_at: '2024-01-01T00:00:00Z',
}

/**
 * Minimal RuntimeEntity — shape from src/api/contracts.ts (RuntimeEntity).
 * InvestigationEntitySearchResponse.items is RuntimeEntity[].
 */
const FAKE_ENTITY = {
  id: 'entity-vendor-001',
  type: 'Vendor',
  properties: { name: 'Acme Medical Supply', npi: '1234567890' },
  metadata: {},
  created_at: '2024-01-01T00:00:00Z',
  updated_at: null,
  version: 1,
}

test.describe('Investigation workbench', () => {
  test('renders search interface and shows entity results after search', async ({ page }) => {
    await mockAuthenticatedShell(page)

    // KnowledgeBasesQuery — InvestigationWorkbenchPage needs at least one KB to
    // render the search controls rather than the "no KB" empty state.
    await page.route(`${API}/knowledgebases`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [FAKE_KB], total: 1 }),
      })
    })

    // Alerts query — InvestigationWorkbenchPage.useAlerts()
    // Returns AlertListResponse (src/api/contracts.ts).
    await page.route(`${API}/alerts`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], page: { page: 1, page_size: 25, total_items: 0 } }),
      })
    })

    // Investigation search — fired when a non-empty search term is set.
    // Endpoint: GET /investigation/search?kb_id=kb-001&q=acme
    // Returns InvestigationEntitySearchResponse (src/api/contracts.ts).
    await page.route(`${API}/investigation/search**`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [FAKE_ENTITY],
          total: 1,
        }),
      })
    })

    await page.goto('/investigation')

    // Page loads and renders the workbench layout (not the "no KB" empty state).
    // SectionHeader title defaults to "Investigation Workbench" when no entity selected.
    await expect(page.getByRole('heading', { name: 'Investigation Workbench' })).toBeVisible()

    // Knowledge base selector is rendered.
    // Source: InvestigationWorkbenchPage — <select id="investigation-kb-select">
    await expect(page.locator('#investigation-kb-select')).toBeVisible()
    await expect(page.locator('#investigation-kb-select')).toHaveValue('kb-001')

    // Entity search input is rendered.
    // Source: InvestigationWorkbenchPage — <input id="investigation-search" type="search">
    const searchInput = page.locator('#investigation-search')
    await expect(searchInput).toBeVisible()

    // Type a search term — triggers useInvestigationEntitySearch when query.length > 0.
    await searchInput.fill('acme')

    // Wait for the mocked search response to resolve and render.
    // The entity appears as a <button class="page-list-item"> in .knowledge-base-documents.
    // Displayed text uses getEntityTitle() — defaults to entity.id when no display config
    // matches, but our FAKE_DOMAIN_CONFIG has a 'Vendor' entity with a 'name' property
    // and the utils use properties.name as the title.
    // Source: src/utils/domainDisplay.ts — getEntityTitle reads the first property.
    await expect(page.getByText('Acme Medical Supply')).toBeVisible()
  })

  test('shows Create KB CTA on the no-KB empty state and navigates on click', async ({
    page,
  }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, [])

    await page.goto('/investigation')

    await expect(page.getByText('No graph-ready knowledge base')).toBeVisible()

    const cta = page.getByRole('button', { name: /create knowledge base/i })
    await expect(cta).toBeVisible()

    await cta.click()

    await expect(page).toHaveURL(/\/knowledge-bases$/)
  })
})
