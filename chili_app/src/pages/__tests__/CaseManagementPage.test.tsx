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
  knowledge_base_id: 'kb-1',
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

const secondUnpromotedAlert = {
  ...alert,
  id: 'alert-3',
  entity_label: 'Cedar Ridge Pharmacy',
  severity: 'medium',
}

const otherKnowledgeBaseAlert = {
  ...alert,
  id: 'alert-other',
  knowledge_base_id: 'kb-2',
  entity_label: 'Out of Scope Lab',
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
      data: { items: [alert, unpromotedAlert, secondUnpromotedAlert], page: { page: 1, page_size: 3, total_items: 3 } },
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
            missing_evidence: ['claims history', 'prior auth'],
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

  it('promotes the clicked unpromoted alert into a case', () => {
    renderPage()

    expect(screen.getByRole('button', { name: 'Promote North Harbor Imaging to case' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Promote Cedar Ridge Pharmacy to case' }))

    expect(mocks.promote).toHaveBeenCalledWith({ alert_id: 'alert-3' }, expect.any(Object))
  })

  it('loads alerts for the selected knowledge base and hides out-of-scope promote actions', () => {
    const alerts = [alert, unpromotedAlert, otherKnowledgeBaseAlert]
    mocks.useAlerts.mockImplementation((filters = {}) => ({
      isLoading: false,
      isError: false,
      data: {
        items: filters.knowledgeBaseId
          ? alerts.filter((item) => item.knowledge_base_id === filters.knowledgeBaseId)
          : alerts,
        page: { page: 1, page_size: alerts.length, total_items: alerts.length },
      },
    }))

    renderPage()

    expect(mocks.useAlerts).toHaveBeenCalledWith({ knowledgeBaseId: 'kb-1' })
    expect(screen.getByRole('button', { name: 'Promote North Harbor Imaging to case' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Promote Out of Scope Lab to case' })).not.toBeInTheDocument()
  })

  it('submits selected analyst feedback values and clears freeform fields', () => {
    renderPage()

    fireEvent.change(screen.getByLabelText('Feedback label'), { target: { value: 'insufficient_evidence' } })
    fireEvent.change(screen.getByLabelText('Evidence adequacy'), { target: { value: 'medium' } })
    fireEvent.change(screen.getByLabelText('Missing evidence'), { target: { value: 'claims history, prior auth' } })

    const notes = screen.getByLabelText('Feedback notes')
    fireEvent.change(notes, { target: { value: 'Need more records.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save feedback' }))

    expect(mocks.addFeedback).toHaveBeenCalledWith(
      {
        label: 'insufficient_evidence',
        evidence_adequacy: 'medium',
        missing_evidence: ['claims history', 'prior auth'],
        notes: 'Need more records.',
      },
      expect.any(Object),
    )
    expect(screen.getByLabelText('Missing evidence')).toHaveValue('')
    expect(notes).toHaveValue('')
    expect(screen.getByLabelText('Feedback label')).toHaveValue('insufficient_evidence')
    expect(screen.getByLabelText('Evidence adequacy')).toHaveValue('medium')
  })

  it('renders complete feedback history fields', () => {
    renderPage()

    expect(screen.getByText('insufficient evidence')).toBeInTheDocument()
    expect(screen.getByText('Evidence adequacy: medium')).toBeInTheDocument()
    expect(screen.getByText('Need more claims history.')).toBeInTheDocument()
    expect(screen.getByText('claims history')).toBeInTheDocument()
    expect(screen.getByText('prior auth')).toBeInTheDocument()
  })
})
