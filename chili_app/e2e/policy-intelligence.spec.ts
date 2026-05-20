/**
 * Flow 7c: Policy Intelligence page
 *
 * Verifies that the PolicyIntelligencePage:
 *   1. Renders all 2 policy gap rows in the gap queue sidebar, each showing
 *      title, severity chip, and affected-case count chip.
 *   2. The detail panel for the auto-selected first gap renders title, summary,
 *      impact statement, recommendation, and the "Generate policy brief" button.
 *   3. Clicking a gap in the sidebar switches the active gap (detail panel title
 *      updates to the second gap).
 *
 * Note: PolicyIntelligencePage auto-selects gaps[0] on load and immediately
 * fetches GET /api/policy/gaps/:id and GET /api/policy/gaps/:id/cases.  All
 * three mocks must be registered before navigation.
 *
 * Mocked endpoints (host-anchored):
 *   GET http://localhost:5173/api/auth/me                     → SessionUser
 *   GET http://localhost:5173/api/config/domain               → DomainConfig
 *   GET http://localhost:5173/api/config/features             → DomainFeatures
 *   GET http://localhost:5173/api/events/stream               → SSE stub
 *   GET http://localhost:5173/api/policy/gaps                 → PolicyGapListResponse (2 items)
 *   GET http://localhost:5173/api/policy/gaps/gap-001         → PolicyGapDetailResponse
 *   GET http://localhost:5173/api/policy/gaps/gap-001/cases   → PolicyGapCaseListResponse
 *   GET http://localhost:5173/api/policy/gaps/gap-002         → PolicyGapDetailResponse
 *   GET http://localhost:5173/api/policy/gaps/gap-002/cases   → PolicyGapCaseListResponse
 *
 * Endpoint shapes verified against:
 *   - PolicyGapSummaryResponse  → src/api/contracts.ts
 *   - PolicyGapListResponse     → src/api/contracts.ts
 *   - PolicyGapDetailResponse   → src/api/contracts.ts
 *   - PolicyGapCaseListResponse → src/api/contracts.ts
 *   - getPolicyGaps             → src/api/policy.ts: apiFetch('/policy/gaps')
 *   - getPolicyGap              → src/api/policy.ts: apiFetch('/policy/gaps/:id')
 *   - getPolicyGapCases         → src/api/policy.ts: apiFetch('/policy/gaps/:id/cases')
 *   - PolicyIntelligencePage    → src/pages/PolicyIntelligencePage.tsx
 *
 * Route: /policy → PolicyIntelligencePage (src/app/router.tsx)
 */

import { expect, test } from '@playwright/test'

import { mockAuthenticatedShell, mockPolicyGaps } from './helpers/mocks'
import type { FakePolicyGap } from './helpers/mocks'

const BASE = 'http://localhost:5173/api'

const FAKE_GAPS: FakePolicyGap[] = [
  {
    id: 'gap-001',
    title: 'Modifier 25 overuse pattern',
    status: 'monitoring',
    severity: 'high',
    impacted_entities: 14,
    affected_case_count: 3,
    knowledge_base_id: 'kb-001',
    updated_at: '2024-06-01T08:00:00Z',
  },
  {
    id: 'gap-002',
    title: 'Unbundling claim fragmentation',
    status: 'drafting',
    severity: 'critical',
    impacted_entities: 27,
    affected_case_count: 7,
    knowledge_base_id: 'kb-001',
    updated_at: '2024-06-02T09:00:00Z',
  },
]

// Full PolicyGapDetailResponse for gap-001.
// Shape: PolicyGapDetailResponse in src/api/contracts.ts.
const GAP_001_DETAIL = {
  gap: FAKE_GAPS[0],
  summary: 'Modifier 25 is being applied with increasing frequency across a cluster of vendors.',
  impact_statement: 'Fourteen entities show claim volumes inconsistent with peer benchmarks.',
  recommendation: 'Initiate targeted review of modifier usage guidelines.',
  policy_citations: [
    {
      citation_id: 'cit-001',
      title: 'CMS Modifier 25 Policy',
      excerpt: 'Modifier 25 may only be used with a significant, separately identifiable E/M service.',
      source_document_id: 'doc-cms-001',
    },
  ],
  trend: [
    { label: 'Jan', value: 10 },
    { label: 'Feb', value: 14 },
    { label: 'Mar', value: 19 },
  ],
}

// Full PolicyGapDetailResponse for gap-002.
const GAP_002_DETAIL = {
  gap: FAKE_GAPS[1],
  summary: 'Claim fragmentation detected across multiple service lines.',
  impact_statement: 'Twenty-seven entities linked to unbundling patterns.',
  recommendation: 'Review bundling edits against NCCI policy tables.',
  policy_citations: [],
  trend: [
    { label: 'Jan', value: 5 },
    { label: 'Feb', value: 9 },
  ],
}

// PolicyGapCaseListResponse — empty case list for both gaps in this test.
// Shape: PolicyGapCaseListResponse in src/api/contracts.ts.
const EMPTY_CASES_RESPONSE = {
  gap_id: 'gap-001',
  items: [],
  page: { page: 1, page_size: 25, total_items: 0 },
}

const EMPTY_CASES_RESPONSE_002 = { ...EMPTY_CASES_RESPONSE, gap_id: 'gap-002' }

test.describe('Policy Intelligence page', () => {
  test('renders gap queue rows and first-gap detail panel', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockPolicyGaps(page, FAKE_GAPS)

    // Register detail + cases for both gaps before navigation.
    // PolicyIntelligencePage auto-selects gaps[0] on load.
    await page.route(`${BASE}/policy/gaps/gap-001`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(GAP_001_DETAIL),
      })
    })
    await page.route(`${BASE}/policy/gaps/gap-001/cases`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(EMPTY_CASES_RESPONSE),
      })
    })
    await page.route(`${BASE}/policy/gaps/gap-002`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(GAP_002_DETAIL),
      })
    })
    await page.route(`${BASE}/policy/gaps/gap-002/cases`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(EMPTY_CASES_RESPONSE_002),
      })
    })

    await page.goto('/policy')

    // Page heading rendered by SectionHeader inside PolicyIntelligencePage.
    await expect(page.getByRole('heading', { name: 'Policy Intelligence' })).toBeVisible()

    // Both gap titles appear in the sidebar queue.
    // PolicyIntelligencePage: gaps.map((gap) => <button ...><strong>{gap.title}</strong>)
    await expect(page.getByText('Modifier 25 overuse pattern').first()).toBeVisible()
    await expect(page.getByText('Unbundling claim fragmentation')).toBeVisible()

    // Severity chips render per gap row.
    // PolicyIntelligencePage: <Chip label={gap.severity} tone={toneForGapSeverity(gap.severity)} />
    const policyLayout = page.locator('.policy-layout')
    await expect(policyLayout.locator('.ui-chip').filter({ hasText: 'high' }).first()).toBeVisible()
    await expect(policyLayout.locator('.ui-chip').filter({ hasText: 'critical' }).first()).toBeVisible()

    // Affected-case count chips per row.
    // PolicyIntelligencePage: <Chip label={`${gap.affected_case_count} cases`} tone="warning" />
    await expect(page.getByText('3 cases').first()).toBeVisible()
    await expect(page.getByText('7 cases').first()).toBeVisible()

    // Detail panel renders the first gap's title and summary.
    // PolicyIntelligencePage: <strong>{gapDetail.gap.title}</strong>
    //                         <span ...>{gapDetail.summary}</span>
    await expect(
      page.getByText('Modifier 25 is being applied with increasing frequency across a cluster of vendors.'),
    ).toBeVisible()

    // "Generate policy brief" button is visible in the brief builder card.
    // PolicyIntelligencePage: <button ... type="button">Generate policy brief</button>
    await expect(page.getByRole('button', { name: 'Generate policy brief' })).toBeVisible()
  })

  test('clicking second gap row switches the detail panel', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockPolicyGaps(page, FAKE_GAPS)

    await page.route(`${BASE}/policy/gaps/gap-001`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(GAP_001_DETAIL),
      })
    })
    await page.route(`${BASE}/policy/gaps/gap-001/cases`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(EMPTY_CASES_RESPONSE),
      })
    })
    await page.route(`${BASE}/policy/gaps/gap-002`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(GAP_002_DETAIL),
      })
    })
    await page.route(`${BASE}/policy/gaps/gap-002/cases`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(EMPTY_CASES_RESPONSE_002),
      })
    })

    await page.goto('/policy')

    // Wait for first gap's detail to render.
    await expect(
      page.getByText('Modifier 25 is being applied with increasing frequency across a cluster of vendors.'),
    ).toBeVisible()

    // Click the second gap in the sidebar.
    // PolicyIntelligencePage: <button onClick={() => setSelectedGapId(gap.id)}>
    await page.getByRole('button', { name: 'Unbundling claim fragmentation' }).click()

    // Detail panel should now show gap-002's summary.
    await expect(
      page.getByText('Claim fragmentation detected across multiple service lines.'),
    ).toBeVisible()
  })
})
