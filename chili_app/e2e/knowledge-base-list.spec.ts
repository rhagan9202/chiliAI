/**
 * Flow 2: Knowledge base list page
 *
 * Verifies that the KnowledgeBaseManagerPage ("Ingestion Studio") renders
 * a list of knowledge bases and the key UI elements when the /knowledgebases
 * endpoint returns rows.
 *
 * Mocked endpoints (host-anchored):
 *   GET http://localhost:5173/api/auth/me                     → SessionUser
 *   GET http://localhost:5173/api/config/domain               → DomainConfig
 *   GET http://localhost:5173/api/config/features             → DomainFeatures
 *   GET http://localhost:5173/api/events/stream               → SSE stub
 *   GET http://localhost:5173/api/knowledgebases              → KnowledgeBaseListResponse
 *   GET http://localhost:5173/api/knowledgebases/kb-001       → KnowledgeBaseSummaryResponse
 *   GET http://localhost:5173/api/knowledgebases/kb-001/documents → KnowledgeBaseDocumentListResponse
 *   GET http://localhost:5173/api/workflows?**                → WorkflowRunListResponse
 *
 * Endpoint paths verified against:
 *   - getKnowledgeBases: src/api/knowledgebases.ts → apiFetch('/knowledgebases')
 *   - getKnowledgeBase: src/api/knowledgebases.ts → apiFetch('/knowledgebases/${id}')
 *   - getKnowledgeBaseDocuments: src/api/knowledgebases.ts → apiFetch('/knowledgebases/${id}/documents')
 *   - getWorkflows: src/api/workflows.ts → apiFetch('/workflows') or '/workflows?knowledge_base_id=...'
 *
 * Response shapes verified against:
 *   - KnowledgeBaseListResponse → src/api/contracts.ts
 *   - KnowledgeBaseSummaryResponse → src/api/contracts.ts
 *   - KnowledgeBaseDocumentListResponse → src/api/contracts.ts
 *   - WorkflowRunListResponse → src/api/contracts.ts
 *
 * Route: /knowledge-bases → KnowledgeBaseManagerPage (router.tsx)
 */

import { test, expect } from '@playwright/test'

import { mockAuthenticatedShell } from './helpers/mocks'

const API = 'http://localhost:5173/api'

const KB_LIST_ITEMS = [
  {
    id: 'kb-001',
    name: 'Medicare FY2024',
    description: 'Claims and providers for FY2024 audit.',
    status: 'ready' as const,
    document_count: 12,
    entity_count: 340,
    relationship_count: 890,
    created_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 'kb-002',
    name: 'Supplemental Reference',
    description: 'Policy documents and coding manuals.',
    status: 'active' as const,
    document_count: 4,
    entity_count: 75,
    relationship_count: 120,
    created_at: '2024-03-01T08:30:00Z',
  },
  {
    id: 'kb-003',
    name: 'Q1 Extracts',
    description: 'Provider extracts for Q1 monitoring.',
    status: 'building' as const,
    document_count: 0,
    entity_count: 0,
    relationship_count: 0,
    created_at: '2024-04-01T12:00:00Z',
  },
]

test.describe('Knowledge base list page', () => {
  test('renders knowledge base rows and create form', async ({ page }) => {
    await mockAuthenticatedShell(page)

    await page.route(`${API}/knowledgebases`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: KB_LIST_ITEMS, total: KB_LIST_ITEMS.length }),
      })
    })

    // KnowledgeBaseManagerPage auto-selects the first KB (kb-001) and fetches
    // its detail + documents. Mock those to avoid loading-guard stalls.
    await page.route(`${API}/knowledgebases/kb-001`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(KB_LIST_ITEMS[0]),
      })
    })

    await page.route(`${API}/knowledgebases/kb-001/documents`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    })

    // Workflows are fetched with an optional ?knowledge_base_id= query param.
    // Use a glob pattern here (not the bare hostname pattern) so both
    // /api/workflows and /api/workflows?knowledge_base_id=... are intercepted.
    // This is safe because the glob only matches after the /api/ prefix and
    // does not match any Vite source module paths (/src/api/...).
    await page.route(`${API}/workflows**`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })

    await page.goto('/knowledge-bases')

    // Page heading from SectionHeader inside KnowledgeBaseManagerPage.
    await expect(page.getByRole('heading', { name: 'Ingestion Studio' })).toBeVisible()

    // KB selector renders each KB as a button inside .ingestion-kb-list.
    // Use .first() because the first KB name also appears in the selected-KB
    // summary panel on the right side of the layout.
    const kbList = page.locator('.ingestion-kb-list')
    await expect(kbList).toBeVisible()
    await expect(kbList.getByText('Medicare FY2024')).toBeVisible()
    await expect(kbList.getByText('Supplemental Reference')).toBeVisible()
    await expect(kbList.getByText('Q1 Extracts')).toBeVisible()

    // Create KB form is always visible — the submit button and the name input.
    // Source: KnowledgeBaseSelector.tsx renders
    //   <button type="submit">Create knowledge base</button> and
    //   <input placeholder="Name" />
    await expect(page.getByRole('button', { name: 'Create knowledge base' })).toBeVisible()
    await expect(page.getByPlaceholder('Name')).toBeVisible()

    // KB count chip rendered in the selector header — "3 knowledge bases".
    // Source: KnowledgeBaseSelector countLabel() function.
    await expect(page.getByText('3 knowledge bases')).toBeVisible()
  })
})
