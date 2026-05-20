/**
 * Shared page.route() mock helpers for e2e tests.
 *
 * IMPORTANT — route pattern discipline:
 *   All API calls from the frontend go through the Vite proxy to
 *   http://localhost:5173/api/... The Playwright browser intercepts these at
 *   the browser level, so patterns must be host-anchored or use glob patterns
 *   that do NOT accidentally match Vite source-module URLs (e.g.
 *   /src/api/client.ts). We use the prefix `http://localhost:5173/api/` to
 *   anchor patterns precisely and avoid the MIME-type error that occurs when
 *   a JS module request is fulfilled as "application/json".
 *
 * All endpoint paths match the actual frontend API client calls:
 *   GET  /api/auth/me                    → src/contexts/SessionContext.tsx: apiRequest('/auth/me')
 *   GET  /api/config/domain              → src/api/config.ts: apiFetch('/config/domain')
 *   GET  /api/config/features            → src/api/config.ts: apiFetch('/config/features')
 *   GET  /api/events/stream              → src/api/realtime.ts: new EventSource('.../events/stream')
 *   GET  /api/alerts                     → src/api/alerts.ts: apiFetch('/alerts')
 *   POST /api/alerts/:id/acknowledge     → src/api/alerts.ts: apiPost('/alerts/:id/acknowledge', {})
 *   GET  /api/knowledgebases             → src/api/knowledgebases.ts: apiFetch('/knowledgebases')
 *   GET  /api/cases                      → src/api/cases.ts: apiFetch('/cases')
 *   GET  /api/cases/:id                  → src/api/cases.ts: apiFetch('/cases/:id')
 *   PATCH /api/cases/:id                 → src/api/cases.ts: apiPatch('/cases/:id', payload)
 *   POST /api/cases/:id/feedback         → src/api/cases.ts: apiPost('/cases/:id/feedback', payload)
 *   GET  /api/policy/gaps                → src/api/policy.ts: apiFetch('/policy/gaps')
 *   GET  /api/policy/gaps/:id            → src/api/policy.ts: apiFetch('/policy/gaps/:id')
 *   GET  /api/policy/gaps/:id/cases      → src/api/policy.ts: apiFetch('/policy/gaps/:id/cases')
 *
 * Shapes verified against:
 *   - SessionUser               → src/contexts/sessionContextValue.ts
 *   - DomainConfig              → src/api/contracts.ts
 *   - DomainFeatures            → src/api/contracts.ts
 *   - AlertListItem             → src/api/contracts.ts
 *   - ApiEnvelope               → src/api/contracts.ts
 *   - CaseSummaryResponse       → src/api/contracts.ts
 *   - CaseDetailResponse        → src/api/contracts.ts
 *   - CaseUpdateRequest         → src/api/contracts.ts
 *   - CaseFeedbackCreateRequest → src/api/contracts.ts
 *   - PolicyGapSummaryResponse  → src/api/contracts.ts
 *   - PolicyGapListResponse     → src/api/contracts.ts
 *   - PolicyGapDetailResponse   → src/api/contracts.ts
 *   - PolicyGapCaseListResponse → src/api/contracts.ts
 */

import type { Page } from '@playwright/test'

/** Minimal valid SessionUser — mirrors src/contexts/sessionContextValue.ts */
export const FAKE_USER = {
  user_id: 'test-user-1',
  roles: ['analyst'],
  email: 'analyst@example.com',
} as const

/**
 * Minimal valid DomainConfig — mirrors src/api/contracts.ts DomainConfig type.
 * Includes ui.navigation so Sidebar renders deterministic nav items.
 */
export const FAKE_DOMAIN_CONFIG = {
  domain: {
    name: 'test_domain',
    display_name: 'Test Domain',
    description: 'A test domain for e2e.',
  },
  entities: [
    {
      name: 'Vendor',
      display_label: 'Vendor',
      properties: {
        name: { type: 'string', display: 'Name', required: true },
      },
    },
  ],
  relationships: [
    {
      name: 'RELATED_TO',
      display_label: 'Related To',
      source: 'Vendor',
      target: 'Vendor',
    },
  ],
  capabilities: {
    timeseries: false,
    gnn: true,
    risk_scoring: true,
    rag_chat: false,
    explainability: false,
    structured_ingestion: false,
  },
  ingestion: {},
  validation: null,
  records: null,
  alerts: {
    thresholds: {},
  },
  ui: {
    default_entity_type: 'Vendor',
    navigation: {
      pages: [
        { id: 'dashboard', label: 'Dashboard', route: '/dashboard' },
        { id: 'alerts', label: 'Alert Feed', route: '/alerts' },
        { id: 'investigation', label: 'Investigation', route: '/investigation' },
        { id: 'knowledge_bases', label: 'Knowledge Bases', route: '/knowledge-bases' },
        { id: 'cases', label: 'Cases', route: '/cases' },
        { id: 'configuration', label: 'Configuration', route: '/configuration' },
      ],
    },
  },
} as const

/**
 * Minimal valid DomainFeatures — mirrors src/api/contracts.ts DomainFeatures type.
 */
export const FAKE_DOMAIN_FEATURES = {
  capabilities: {
    timeseries: false,
    gnn: true,
    risk_scoring: true,
    rag_chat: false,
    explainability: false,
    structured_ingestion: false,
  },
  default_entity_type: 'Vendor',
  default_role: 'analyst',
  enabled_pages: [
    'dashboard',
    'alerts',
    'investigation',
    'knowledge_bases',
    'cases',
    'configuration',
  ],
  roles: {
    analyst: {
      landing_page: 'dashboard',
      pages: [
        'dashboard',
        'alerts',
        'investigation',
        'knowledge_bases',
        'cases',
        'configuration',
      ],
      permissions: ['read', 'write'],
    },
  },
} as const

const BASE = 'http://localhost:5173/api'

/**
 * Mock GET /api/auth/me → authenticated user.
 * Pattern is host-anchored to prevent accidentally matching Vite source URLs
 * like /src/api/client.ts (see module-level comment).
 * Verified shape: SessionUser in src/contexts/sessionContextValue.ts
 */
export async function mockAuthenticated(page: Page): Promise<void> {
  await page.route(`${BASE}/auth/me`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FAKE_USER),
    })
  })
}

/**
 * Mock GET /api/config/domain → minimal DomainConfig.
 * Verified shape: DomainConfig in src/api/contracts.ts
 */
export async function mockDomainConfig(page: Page): Promise<void> {
  await page.route(`${BASE}/config/domain`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FAKE_DOMAIN_CONFIG),
    })
  })
}

/**
 * Mock GET /api/config/features → minimal DomainFeatures.
 * Verified shape: DomainFeatures in src/api/contracts.ts
 */
export async function mockDomainFeatures(page: Page): Promise<void> {
  await page.route(`${BASE}/config/features`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FAKE_DOMAIN_FEATURES),
    })
  })
}

/**
 * Mock the SSE stream /api/events/stream.
 * AppShell calls useRealtimeWorkspaceStream which opens an EventSource here.
 * Returning an empty SSE response lets the connection resolve without hanging.
 * Verified source: src/api/realtime.ts
 */
export async function mockEventsStream(page: Page): Promise<void> {
  await page.route(`${BASE}/events/stream`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: '',
    })
  })
}

/**
 * Apply all mocks needed for the authenticated AppShell to render.
 * Call this before navigating to any protected route.
 */
export async function mockAuthenticatedShell(page: Page): Promise<void> {
  await mockAuthenticated(page)
  await mockDomainConfig(page)
  await mockDomainFeatures(page)
  await mockEventsStream(page)
}

// ---------------------------------------------------------------------------
// Reusable payload shapes — verified against src/api/contracts.ts
// ---------------------------------------------------------------------------

/** Minimal AlertListItem — mirrors AlertListItem in src/api/contracts.ts */
export type FakeAlert = {
  id: string
  entity_id: string
  entity_type: string
  entity_label: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed'
  title: string
  reasoning: string
  confidence: number
  evidence_pack_id: string | null
  created_at: string
  tags: string[]
}

/**
 * Mock GET /api/alerts → AlertListResponse.
 * Endpoint path verified: src/api/alerts.ts → apiFetch('/alerts')
 * Response shape verified: AlertListResponse in src/api/contracts.ts
 */
export async function mockAlerts(page: Page, alerts: FakeAlert[]): Promise<void> {
  await page.route(`${BASE}/alerts`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: alerts,
        page: { page: 1, page_size: 25, total_items: alerts.length },
      }),
    })
  })
}

/** Minimal CaseSummaryResponse — mirrors CaseSummaryResponse in src/api/contracts.ts */
export type FakeCase = {
  id: string
  title: string
  status: 'open' | 'in_review' | 'closed'
  priority: 'low' | 'medium' | 'high' | 'critical'
  assignee: string | null
  alert_ids: string[]
  updated_at: string
}

/**
 * Mock GET /api/cases → CaseListResponse.
 * Endpoint path verified: src/api/cases.ts → apiFetch('/cases')
 * Response shape verified: CaseListResponse in src/api/contracts.ts
 */
export async function mockCases(page: Page, cases: FakeCase[]): Promise<void> {
  await page.route(`${BASE}/cases`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: cases,
        page: { page: 1, page_size: 25, total_items: cases.length },
      }),
    })
  })
}

/** Minimal KnowledgeBaseSummaryResponse — mirrors src/api/contracts.ts */
export type FakeKnowledgeBase = {
  id: string
  name: string
  description: string
  status: 'active' | 'building' | 'ready' | 'error' | 'archived'
  document_count: number
  entity_count: number
  relationship_count: number
  created_at: string
}

/**
 * Mock GET /api/knowledgebases → KnowledgeBaseListResponse.
 * Endpoint path verified: src/api/knowledgebases.ts → apiFetch('/knowledgebases')
 * Response shape verified: KnowledgeBaseListResponse in src/api/contracts.ts
 */
export async function mockKnowledgeBases(
  page: Page,
  knowledgeBases: FakeKnowledgeBase[],
): Promise<void> {
  await page.route(`${BASE}/knowledgebases`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: knowledgeBases, total: knowledgeBases.length }),
    })
  })
}

/**
 * Minimal PolicyGapSummaryResponse — mirrors PolicyGapSummaryResponse in
 * src/api/contracts.ts.
 */
export type FakePolicyGap = {
  id: string
  title: string
  status: 'monitoring' | 'drafting' | 'recommended'
  severity: 'medium' | 'high' | 'critical'
  impacted_entities: number
  affected_case_count: number
  knowledge_base_id: string
  updated_at: string
}

/**
 * Mock GET /api/policy/gaps → PolicyGapListResponse.
 * Endpoint path verified: src/api/policy.ts → apiFetch('/policy/gaps')
 * Response shape verified: PolicyGapListResponse in src/api/contracts.ts
 */
export async function mockPolicyGaps(page: Page, gaps: FakePolicyGap[]): Promise<void> {
  await page.route(`${BASE}/policy/gaps`, (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: gaps,
        page: { page: 1, page_size: 25, total_items: gaps.length },
      }),
    })
  })
}
