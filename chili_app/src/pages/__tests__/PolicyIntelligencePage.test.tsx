import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PolicyIntelligencePage } from '../PolicyIntelligencePage'

const mocks = vi.hoisted(() => ({
  createBrief: vi.fn(),
  usePolicyGap: vi.fn(),
  usePolicyGapCases: vi.fn(),
  usePolicyGaps: vi.fn(),
}))

vi.mock('../../api/policy', () => ({
  useCreatePolicyBrief: () => ({ data: undefined, isPending: false, mutate: mocks.createBrief }),
  usePolicyGap: mocks.usePolicyGap,
  usePolicyGapCases: mocks.usePolicyGapCases,
  usePolicyGaps: mocks.usePolicyGaps,
}))

const gapSummary = {
  id: 'gap-1',
  title: 'Medical necessity documentation gap',
  status: 'monitoring',
  severity: 'high',
  impacted_entities: 18,
  affected_case_count: 3,
  knowledge_base_id: 'kb-1',
  updated_at: '2026-05-12T12:00:00Z',
}

const caseSummary = {
  id: 'case-1',
  title: 'Redwood DME escalation',
  status: 'open',
  priority: 'high',
  assignee: 'J. Chen',
  alert_ids: ['alert-1'],
  updated_at: '2026-05-12T00:00:00Z',
}

describe('PolicyIntelligencePage', () => {
  beforeEach(() => {
    mocks.createBrief.mockReset()
    mocks.usePolicyGaps.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [gapSummary], page: { page: 1, page_size: 1, total_items: 1 } },
    })
    mocks.usePolicyGap.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        gap: gapSummary,
        summary: 'Documentation evidence is inconsistent across high-risk claims.',
        impact_statement: 'Investigators spend extra review time resolving policy ambiguity.',
        recommendation: 'Update guidance with explicit documentation examples.',
        policy_citations: [
          {
            citation_id: 'policy-1',
            title: 'CMS Billing Integrity Manual',
            excerpt: 'Claims require documented medical necessity.',
            source_document_id: 'doc-policy-1',
          },
        ],
        trend: [
          { label: 'Q1', value: 4 },
          { label: 'Q2', value: 9 },
        ],
      },
    })
    mocks.usePolicyGapCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { gap_id: 'gap-1', items: [caseSummary], page: { page: 1, page_size: 1, total_items: 1 } },
    })
  })

  it('renders policy gap details, citations, trends, and affected cases', () => {
    render(<PolicyIntelligencePage />)

    expect(screen.getByText('Policy Intelligence')).toBeInTheDocument()
    expect(screen.getAllByText('Medical necessity documentation gap')).toHaveLength(2)
    expect(screen.getByText('CMS Billing Integrity Manual')).toBeInTheDocument()
    expect(screen.getByText('Gap trend')).toBeInTheDocument()
    expect(screen.getByText('Redwood DME escalation')).toBeInTheDocument()
  })

  it('sends current brief-builder inputs to the mutation', () => {
    render(<PolicyIntelligencePage />)

    fireEvent.change(screen.getByPlaceholderText('Audience'), {
      target: { value: 'Program integrity leadership' },
    })
    fireEvent.change(screen.getByPlaceholderText('Describe the policy brief objective'), {
      target: { value: 'Explain policy options.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Generate policy brief' }))

    expect(mocks.createBrief).toHaveBeenCalledWith({
      gap_id: 'gap-1',
      audience: 'Program integrity leadership',
      objective: 'Explain policy options.',
    })
  })

  it('renders a no-gap empty state', () => {
    mocks.usePolicyGaps.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], page: { page: 1, page_size: 0, total_items: 0 } },
    })

    render(<PolicyIntelligencePage />)

    expect(screen.getByText('No policy gaps detected')).toBeInTheDocument()
  })
})
