import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAppStore } from '../../stores/appStore'
import { CaseManagementPage } from '../CaseManagementPage'

const mocks = vi.hoisted(() => ({
  addFeedback: vi.fn(),
  downloadTextFile: vi.fn(),
  exportCaseDossier: vi.fn(),
  promote: vi.fn(),
  updateCase: vi.fn(),
  useAlerts: vi.fn(),
  useCase: vi.fn(),
  useCaseDossier: vi.fn(),
  useCases: vi.fn(),
  useKnowledgeBases: vi.fn(),
  useDomainConfig: vi.fn(),
}))

vi.mock('../../api/alerts', () => ({
  useAlerts: mocks.useAlerts,
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: mocks.useKnowledgeBases,
}))

vi.mock('../../api/config', () => ({
  useDomainConfig: mocks.useDomainConfig,
}))

vi.mock('../../api/cases', () => ({
  useAddCaseFeedback: () => ({ mutate: mocks.addFeedback }),
  useCase: mocks.useCase,
  useCaseDossier: mocks.useCaseDossier,
  useCases: mocks.useCases,
  exportCaseDossier: mocks.exportCaseDossier,
  usePromoteCase: () => ({ mutate: mocks.promote, isPending: false }),
  useUpdateCase: () => ({ mutate: mocks.updateCase }),
}))

vi.mock('../../utils/downloadFile', async () => {
  const actual = await vi.importActual<typeof import('../../utils/downloadFile')>(
    '../../utils/downloadFile',
  )
  return { ...actual, downloadTextFile: mocks.downloadTextFile }
})

const caseSummary = {
  id: 'case-1',
  knowledge_base_id: 'kb-1',
  title: 'Redwood DME escalation',
  status: 'open',
  priority: 'high',
  assignee: 'J. Chen',
  alert_ids: ['alert-1'],
  evidence_pack_id: 'evidence-1',
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

function LocationProbe({ onChange }: { onChange: (location: string) => void }) {
  const location = useLocation()
  onChange(`${location.pathname}${location.search}`)
  return null
}

function renderPageWithLocationProbe(initialEntry = '/cases?kb=kb-1&case=case-1') {
  const locations: string[] = []
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <CaseManagementPage />
      <LocationProbe onChange={(location) => locations.push(location)} />
    </MemoryRouter>,
  )
  return locations
}

describe('CaseManagementPage', () => {
  beforeEach(() => {
    mocks.addFeedback.mockReset()
    mocks.downloadTextFile.mockReset()
    mocks.exportCaseDossier.mockReset()
    mocks.promote.mockReset()
    mocks.updateCase.mockReset()
    // Query mocks keep their implementation but must forget prior calls, or a
    // `toHaveBeenCalledWith` assertion can pass on another test's call.
    mocks.useCases.mockClear()
    mocks.useAlerts.mockClear()
    mocks.useKnowledgeBases.mockClear()
    window.localStorage.clear()
    useAppStore.setState({ activeKnowledgeBaseId: null })
    mocks.useDomainConfig.mockReturnValue({
      data: { domain: { name: 'medicare_fraud' } },
    })
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
        alerts: [{ ...alert, evidence_pack_id: 'alert-evidence-should-not-be-used' }],
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
    mocks.useCaseDossier.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: caseSummary,
        alerts: [alert],
        evidence_packs: [
          {
            id: 'evidence-1',
            alert_id: 'alert-1',
            reasoning: 'Originating alert evidence.',
            confidence: 0.91,
            scores: {},
            subgraph_node_ids: ['provider-204'],
            subgraph_edge_ids: [],
            attribution: [],
            narrative_sections: [],
            provenance: [
              {
                reference_type: 'document',
                reference_id: 'source-doc#0',
                label: 'Origin claim source',
                source_system: 'cms-claims',
                source_version: '2026-08-demo',
                transformation_version: 'safe-cms-008-test',
                confidence: 0.91,
                route_target: '/knowledgebases/kb-1/documents/source-doc/preview',
                metadata: { document_id: 'source-doc' },
              },
            ],
            created_at: '2026-05-12T00:00:00Z',
            source_documents: ['source-doc'],
          },
        ],
        entity_timeline: [
          { occurred_at: '2026-05-12T00:00:00Z', label: 'alert_raised', detail: 'Outlier billing concentration' },
        ],
        feedback_history: [
          {
            case_id: 'case-1',
            label: 'insufficient_evidence',
            evidence_adequacy: 'medium',
            missing_evidence: ['claims history'],
            notes: 'Need more claims history.',
            submitted_at: '2026-05-12T00:00:00Z',
          },
        ],
        audit_events: [
          {
            event_id: 'audit-feedback',
            occurred_at: '2026-05-12T00:03:00Z',
            tenant_id: 'kb-1',
            knowledge_base_id: 'kb-1',
            actor_user_id: 'analyst-42',
            actor_email: 'analyst42@example.test',
            actor_roles: ['analyst'],
            action: 'case.feedback.create',
            resource_type: 'case',
            resource_id: 'case-1',
            before: { feedback_count: 0 },
            after: { feedback_count: 1, label: 'insufficient_evidence' },
            correlation_id: 'cases:kb-1:case.feedback.create:case-1',
            outcome: 'success',
            metadata: { source: 'api.cases' },
          },
          {
            event_id: 'audit-promote',
            occurred_at: '2026-05-12T00:01:00Z',
            tenant_id: 'kb-1',
            knowledge_base_id: 'kb-1',
            actor_user_id: 'analyst-42',
            actor_email: 'analyst42@example.test',
            actor_roles: ['analyst'],
            action: 'case.promote',
            resource_type: 'case',
            resource_id: 'case-1',
            before: null,
            after: { status: 'open', priority: 'critical' },
            correlation_id: 'cases:kb-1:case.promote:case-1',
            outcome: 'success',
            metadata: { source: 'api.cases' },
          },
        ],
        export: { formats: ['markdown', 'json'], default_filename: 'case-case-1.md' },
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

  it('updates the case query parameter after promoting an alert while another valid case is selected', () => {
    mocks.promote.mockImplementation((_payload, options) => {
      options.onSuccess({
        case: {
          ...caseSummary,
          id: 'case-new',
          title: 'North Harbor Imaging escalation',
          alert_ids: ['alert-2'],
          evidence_pack_id: 'evidence-2',
        },
      })
    })
    const locations = renderPageWithLocationProbe('/cases?kb=kb-1&case=case-1')

    fireEvent.click(screen.getByRole('button', { name: 'Promote North Harbor Imaging to case' }))

    expect(locations.at(-1)).toBe('/cases?kb=kb-1&case=case-new')
  })

  it('launches Ask AI with the active case context', () => {
    const locations = renderPageWithLocationProbe()

    fireEvent.click(screen.getByRole('button', { name: 'Ask AI for Redwood DME escalation' }))

    expect(locations.at(-1)).toBe(
      '/rag-chat?kb=kb-1&source=case&alert=alert-1&case=case-1&evidence=evidence-1&q=Why+is+this+high+risk%3F',
    )
  })

  it('links the selected case back to the investigation cockpit with full context', () => {
    renderPage()

    expect(screen.getByRole('link', { name: 'Open cockpit' })).toHaveAttribute(
      'href',
      '/investigation/provider-204?kb=kb-1&alert=alert-1&case=case-1&evidence=evidence-1',
    )
  })

  it('keeps the cockpit link alert, entity, and evidence from one usable case alert', () => {
    mocks.useCase.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        case: {
          ...caseSummary,
          alert_ids: ['alert-missing', 'alert-2'],
          evidence_pack_id: 'case-evidence-for-missing-alert',
          originating_alert_id: 'alert-missing',
        },
        alerts: [
          {
            ...unpromotedAlert,
            id: 'alert-2',
            entity_id: 'provider-777',
            evidence_pack_id: 'evidence-2',
          },
        ],
        evidence_pack: null,
        entity_timeline: [],
        feedback_history: [],
      },
    })

    renderPage()

    expect(screen.getByRole('link', { name: 'Open cockpit' })).toHaveAttribute(
      'href',
      '/investigation/provider-777?kb=kb-1&alert=alert-2&case=case-1&evidence=evidence-2',
    )
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

    expect(screen.getAllByText('insufficient evidence').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Evidence adequacy: medium').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Need more claims history.').length).toBeGreaterThan(0)
    expect(screen.getByText('claims history')).toBeInTheDocument()
    expect(screen.getByText('prior auth')).toBeInTheDocument()
  })

  it('renders a case dossier with evidence, chronology, decisions, and export actions', () => {
    renderPage()

    expect(mocks.useCaseDossier).toHaveBeenCalledWith('kb-1', 'case-1')
    const dossier = screen.getByRole('region', { name: 'Case dossier' })
    expect(within(dossier).getByText('Evidence bundle')).toBeInTheDocument()
    expect(within(dossier).getByText('Originating alert evidence.')).toBeInTheDocument()
    expect(within(dossier).getByText('Origin claim source')).toBeInTheDocument()
    expect(within(dossier).getByText('Chronology')).toBeInTheDocument()
    expect(within(dossier).getByText('Decisions')).toBeInTheDocument()
    expect(within(dossier).getByText('Audit trail')).toBeInTheDocument()
    expect(within(dossier).getByText('case feedback create')).toBeInTheDocument()
    expect(within(dossier).getByText('case promote')).toBeInTheDocument()
    expect(within(dossier).getAllByText('analyst42@example.test')).toHaveLength(2)
    expect(within(dossier).getByRole('button', { name: 'Export dossier Markdown' })).toBeInTheDocument()
    expect(within(dossier).getByRole('button', { name: 'Export dossier JSON' })).toBeInTheDocument()
  })

  it('downloads case dossier exports through the case export endpoint', async () => {
    mocks.exportCaseDossier.mockResolvedValue({
      case_id: 'case-1',
      knowledge_base_id: 'kb-1',
      format: 'markdown',
      filename: 'case-case-1.md',
      content: '# Redwood DME escalation',
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Export dossier Markdown' }))

    await waitFor(() => {
      expect(mocks.exportCaseDossier).toHaveBeenCalledWith('kb-1', 'case-1', 'markdown')
    })
    expect(mocks.downloadTextFile).toHaveBeenCalledWith(
      'case-case-1.md',
      '# Redwood DME escalation',
      'text/markdown',
    )
  })

  it('expresses "open or in review" in one view', () => {
    // The single-select chip row could only ever show one status (UXA-401).
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          caseSummary,
          { ...caseSummary, id: 'case-2', title: 'North Harbor review', status: 'in_review' },
          { ...caseSummary, id: 'case-3', title: 'Cedar Ridge closure', status: 'closed' },
        ],
        page: { page: 1, page_size: 3, total_items: 3 },
      },
    })

    render(
      <MemoryRouter initialEntries={['/cases?kb=kb-1&status=open&status=in_review']}>
        <CaseManagementPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Showing 2 of 3 cases')).toBeInTheDocument()
    expect(screen.queryByText('Cedar Ridge closure')).not.toBeInTheDocument()
  })

  it('shows a count on every status option', () => {
    renderPage()

    expect(screen.getByRole('button', { name: 'Open, 1 matching' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Closed, 0 matching' })).toBeInTheDocument()
  })

  it('offers a way out of a filter that matched nothing', () => {
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [caseSummary], page: { page: 1, page_size: 1, total_items: 1 } },
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Closed, 0 matching' }))

    expect(screen.getByText('No cases match this filter')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }))

    expect(screen.getAllByText('Redwood DME escalation').length).toBeGreaterThan(0)
  })

  it('points at the alert queue when there are no cases at all', () => {
    // "Filtered to nothing" and "nothing here yet" are different problems and
    // need different next steps (UXA-305).
    mocks.useCases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], page: { page: 1, page_size: 0, total_items: 0 } },
    })

    renderPage()

    expect(screen.getByText('No cases yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /alert feed/i })).toHaveAttribute(
      'href',
      '/alerts?kb=kb-1',
    )
  })

  it('scopes to the shared active knowledge base, not the first one listed', () => {
    // The list order puts the stale KB first; the workspace default is the most
    // recently updated one, which is what the Dashboard also reports on.
    mocks.useKnowledgeBases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          { id: 'kb-stale', name: 'Stale', updated_at: '2026-01-01T00:00:00Z', domain: 'medicare_fraud' },
          { id: 'kb-current', name: 'Current', updated_at: '2026-07-01T00:00:00Z', domain: 'medicare_fraud' },
        ],
      },
    })

    render(
      <MemoryRouter initialEntries={['/cases']}>
        <CaseManagementPage />
      </MemoryRouter>,
    )

    expect(mocks.useCases).toHaveBeenCalledWith('kb-current')
  })

  it('honors the remembered knowledge base across pages', () => {
    // `kb-current` is both first in the list and the most recent, so only the
    // remembered selection can produce `kb-stale` here.
    useAppStore.setState({ activeKnowledgeBaseId: 'kb-stale' })
    mocks.useKnowledgeBases.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          { id: 'kb-current', name: 'Current', updated_at: '2026-07-01T00:00:00Z', domain: 'medicare_fraud' },
          { id: 'kb-stale', name: 'Stale', updated_at: '2026-01-01T00:00:00Z', domain: 'medicare_fraud' },
        ],
      },
    })

    render(
      <MemoryRouter initialEntries={['/cases']}>
        <CaseManagementPage />
      </MemoryRouter>,
    )

    expect(mocks.useCases).toHaveBeenCalledWith('kb-stale')
  })
})
