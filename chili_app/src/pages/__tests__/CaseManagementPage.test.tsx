import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CaseManagementPage } from '../CaseManagementPage'

const mocks = vi.hoisted(() => ({
  addFeedback: vi.fn(),
  createCase: vi.fn(),
  updateCase: vi.fn(),
  useAlerts: vi.fn(),
  useCase: vi.fn(),
  useCases: vi.fn(),
}))

vi.mock('../../api/alerts', () => ({
  useAlerts: mocks.useAlerts,
}))

vi.mock('../../api/cases', () => ({
  useAddCaseFeedback: () => ({ mutate: mocks.addFeedback }),
  useCase: mocks.useCase,
  useCases: mocks.useCases,
  useCreateCase: () => ({ mutate: mocks.createCase }),
  useUpdateCase: () => ({ mutate: mocks.updateCase }),
}))

const caseSummary = {
  id: 'case-1',
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

const unassignedAlert = {
  ...alert,
  id: 'alert-2',
  entity_label: 'North Harbor Imaging',
  severity: 'high',
}

describe('CaseManagementPage', () => {
  beforeEach(() => {
    mocks.addFeedback.mockReset()
    mocks.createCase.mockReset()
    mocks.updateCase.mockReset()
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [caseSummary], page: { page: 1, page_size: 1, total_items: 1 } },
    })
    mocks.useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [alert, unassignedAlert], page: { page: 1, page_size: 2, total_items: 2 } },
    })
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: caseSummary,
        alerts: [alert],
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
    render(<CaseManagementPage />)

    expect(screen.getByText('Case Management')).toBeInTheDocument()
    expect(screen.getAllByText('Redwood DME escalation')).toHaveLength(2)
    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Mark in review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close case' }))

    expect(mocks.updateCase).toHaveBeenNthCalledWith(1, { status: 'in_review' })
    expect(mocks.updateCase).toHaveBeenNthCalledWith(2, { status: 'closed' })
  })

  it('creates a case from an unassigned alert', () => {
    render(<CaseManagementPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Create case from North Harbor Imaging' }))

    expect(mocks.createCase).toHaveBeenCalledWith({
      title: 'North Harbor Imaging review',
      priority: 'high',
      assignee: 'Unassigned',
      alert_ids: ['alert-2'],
    })
  })

  it('submits analyst feedback and clears the textarea', () => {
    render(<CaseManagementPage />)

    const textarea = screen.getByPlaceholderText('Document the current evidence assessment')
    fireEvent.change(textarea, { target: { value: 'Evidence supports escalation.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save suspicious finding' }))

    expect(mocks.addFeedback).toHaveBeenCalledWith({
      label: 'suspicious',
      evidence_adequacy: 'high',
      missing_evidence: [],
      notes: 'Evidence supports escalation.',
    })
    expect(textarea).toHaveValue('')
  })
})
