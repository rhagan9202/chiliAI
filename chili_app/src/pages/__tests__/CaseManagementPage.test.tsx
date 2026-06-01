import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CaseManagementPage } from '../CaseManagementPage'

const mocks = vi.hoisted(() => ({
  addFeedback: vi.fn(),
  promote: vi.fn(),
  updateCase: vi.fn(),
  useAlerts: vi.fn(),
  useCase: vi.fn(),
  useCases: vi.fn(),
  useKnowledgeBases: vi.fn(),
}))

vi.mock('../../api/alerts', () => ({
  useAlerts: mocks.useAlerts,
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: mocks.useKnowledgeBases,
}))

vi.mock('../../api/cases', () => ({
  useAddCaseFeedback: () => ({ mutate: mocks.addFeedback }),
  useCase: mocks.useCase,
  useCases: mocks.useCases,
  usePromoteCase: () => ({ mutate: mocks.promote, isPending: false }),
  useUpdateCase: () => ({ mutate: mocks.updateCase }),
}))

const caseSummary = {
  id: 'case-1',
  knowledge_base_id: 'kb-1',
  title: 'Redwood DME escalation',
  status: 'open',
  priority: 'high',
  assignee: 'J. Chen',
  alert_ids: ['alert-1'],
  updated_at: '2026-05-12T00:00:00Z',
}

const alert = {
  id: 'alert-1',
  entity_id: 'provider-204',
  entity_type: 'provider',
  entity_label: 'Redwood DME Group',
  severity: 'critical',
  status: 'open',
  title: 'Outlier billing concentration',
  reasoning: 'Provider activity is materially above peers.',
  confidence: 0.96,
  evidence_pack_id: 'evidence-1',
  created_at: '2026-05-12T00:00:00Z',
  tags: ['billing'],
}

const unpromotedAlert = {
  ...alert,
  id: 'alert-2',
  entity_label: 'North Harbor Imaging',
  severity: 'high',
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/cases?kb=kb-1']}>
      <CaseManagementPage />
    </MemoryRouter>,
  )
}

describe('CaseManagementPage', () => {
  beforeEach(() => {
    mocks.addFeedback.mockReset()
    mocks.promote.mockReset()
    mocks.updateCase.mockReset()
    mocks.useKnowledgeBases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [{ id: 'kb-1', name: 'Medicare' }] },
    })
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [caseSummary], page: { page: 1, page_size: 1, total_items: 1 } },
    })
    mocks.useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [alert, unpromotedAlert], page: { page: 1, page_size: 2, total_items: 2 } },
    })
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: caseSummary,
        alerts: [alert],
        evidence_pack: null,
        entity_timeline: [
          { occurred_at: '2026-05-12T00:00:00Z', label: 'alert_raised', detail: 'Outlier billing concentration' },
        ],
        feedback_history: [
          {
            case_id: 'case-1',
            label: 'insufficient_evidence',
            evidence_adequacy: 'medium',
            missing_evidence: [],
            notes: 'Need more claims history.',
            submitted_at: '2026-05-12T00:00:00Z',
          },
        ],
      },
    })
  })

  it('renders case queue, detail, and mutation controls', () => {
    renderPage()

    expect(screen.getByText('Case Management')).toBeInTheDocument()
    expect(screen.getAllByText('Redwood DME escalation')).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: 'Mark in review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close case' }))

    expect(mocks.updateCase).toHaveBeenNthCalledWith(1, { status: 'in_review' }, expect.anything())
    expect(mocks.updateCase).toHaveBeenNthCalledWith(2, { status: 'closed' }, expect.anything())
  })

  it('promotes an unpromoted alert into a case', () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Promote North Harbor Imaging to case' }))

    expect(mocks.promote).toHaveBeenCalledWith({ alert_id: 'alert-2' }, expect.anything())
  })

  it('submits analyst feedback and clears the textarea', () => {
    renderPage()

    const textarea = screen.getByPlaceholderText('Document the current evidence assessment')
    fireEvent.change(textarea, { target: { value: 'Evidence supports escalation.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save suspicious finding' }))

    expect(mocks.addFeedback).toHaveBeenCalledWith(
      {
        label: 'suspicious',
        evidence_adequacy: 'high',
        missing_evidence: [],
        notes: 'Evidence supports escalation.',
      },
      expect.anything(),
    )
    expect(textarea).toHaveValue('')
  })
})
