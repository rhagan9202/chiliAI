import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DashboardPage } from '../DashboardPage'

// Smoke test demonstrating the contract-mocking pattern for Phase 5 pages.
// Each page hits its own React Query hooks; mocking them here keeps the
// smoke isolated from the network and from the shared QueryClient.

vi.mock('../../api/alerts', () => ({
  useAlerts: () => ({
    isLoading: false,
    isError: false,
    data: {
      items: [
        {
          id: 'alert-1',
          entity_id: 'provider-204',
          entity_type: 'provider',
          entity_label: 'Advanced Pain Specialists',
          severity: 'high',
          status: 'open',
          title: 'Provider risk threshold exceeded',
          reasoning: 'Aggregate risk score breached configured threshold.',
          confidence: 0.85,
          evidence_pack_id: 'evidence-001',
          created_at: new Date().toISOString(),
          tags: ['provider', 'risk-spike'],
        },
      ],
      page: { page: 1, page_size: 1, total_items: 1 },
    },
  }),
}))

vi.mock('../../api/analytics', () => ({
  useAnalyticsOverview: () => ({
    isLoading: false,
    isError: false,
    data: { active_alerts: 4, high_risk_entities: 2, entities_monitored: 12, open_cases: 3 },
  }),
}))

vi.mock('../../api/workflows', () => ({
  useWorkflows: () => ({
    isLoading: false,
    isError: false,
    data: {
      items: [{ id: 'wf-1', status: 'completed', kind: 'ingestion', updated_at: new Date().toISOString() }],
      page: { page: 1, page_size: 1, total_items: 1 },
    },
  }),
}))

describe('DashboardPage', () => {
  it('renders KPI cards using the api.contracts shape', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Active alerts')).toBeInTheDocument()
    // value=4 from useAnalyticsOverview mock
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('renders the lead alert from the alerts feed', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Advanced Pain Specialists')).toBeInTheDocument()
  })
})
