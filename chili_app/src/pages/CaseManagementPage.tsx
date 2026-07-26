import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { useAlerts } from '../api/alerts'
import { useAddCaseFeedback, useCase, useCases, usePromoteCase, useUpdateCase } from '../api/cases'
import type { CaseFeedbackCreateRequest } from '../api/contracts'
import { useKnowledgeBases } from '../api/knowledgebases'
import { showToast } from '../components/common/toastStore'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterBar } from '../components/ui/FilterBar'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { buildRagChatUrl, DEFAULT_RISK_QUESTION } from '../lib/ragContext'
import './pages.css'

type StatusFilter = 'all' | 'open' | 'in_review' | 'closed'

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'Open' },
  { id: 'in_review', label: 'In review' },
  { id: 'closed', label: 'Closed' },
]

export function CaseManagementPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const requestedKbId = searchParams.get('kb')
  const requestedCaseId = searchParams.get('case')
  const knowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
    ? requestedKbId
    : knowledgeBases[0]?.id ?? null

  const casesQuery = useCases(knowledgeBaseId)
  const alertsQuery = useAlerts({ knowledgeBaseId: knowledgeBaseId ?? undefined })
  const promoteMutation = usePromoteCase(knowledgeBaseId)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const activeCaseId = casesQuery.data?.items.some((caseItem) => caseItem.id === requestedCaseId)
    ? requestedCaseId
    : selectedCaseId ?? casesQuery.data?.items[0]?.id ?? null
  const caseQuery = useCase(knowledgeBaseId, activeCaseId)
  const updateCaseMutation = useUpdateCase(knowledgeBaseId, activeCaseId)
  const feedbackMutation = useAddCaseFeedback(knowledgeBaseId, activeCaseId)
  const [feedbackLabel, setFeedbackLabel] = useState<CaseFeedbackCreateRequest['label']>('suspicious')
  const [evidenceAdequacy, setEvidenceAdequacy] =
    useState<CaseFeedbackCreateRequest['evidence_adequacy']>('high')
  const [missingEvidence, setMissingEvidence] = useState('')
  const [feedbackNotes, setFeedbackNotes] = useState('')

  if (knowledgeBasesQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesQuery.isError) {
    return <ErrorState description="Knowledge base inventory could not be loaded from the backend." />
  }

  if (!knowledgeBaseId) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Human feedback loop"
          subtitle="Create or select a knowledge base to manage its investigation cases."
          title="Case Management"
        />
        <Card>
          <EmptyState
            description="Cases are scoped to a knowledge base. Select one to view its queue."
            title="No knowledge base selected"
          />
        </Card>
      </section>
    )
  }

  if (casesQuery.isLoading || alertsQuery.isLoading) {
    return <LoadingState label="Loading case queue" />
  }

  if (casesQuery.isError || alertsQuery.isError) {
    return <ErrorState description="Case management data could not be loaded from the backend." />
  }

  if (!casesQuery.data || !alertsQuery.data) {
    return <LoadingState label="Waiting for case data" />
  }

  const visibleCases =
    statusFilter === 'all'
      ? casesQuery.data.items
      : casesQuery.data.items.filter((caseItem) => caseItem.status === statusFilter)

  const unpromotedAlerts = alertsQuery.data.items.filter(
    (alert) => !casesQuery.data.items.some((existingCase) => existingCase.alert_ids.includes(alert.id)),
  )

  const handleUpdate = (status: 'in_review' | 'closed') => {
    updateCaseMutation.mutate(
      { status },
      {
        onSuccess: () => showToast('success', `Case marked ${status.replace(/_/g, ' ')}.`),
        onError: () => showToast('error', 'Could not update the case.'),
      },
    )
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${casesQuery.data.page.total_items} cases`} tone="info" />}
        eyebrow="Human feedback loop"
        subtitle="Cases persist durably per knowledge base and can be promoted from alerts with their evidence."
        title="Case Management"
      />

      <FilterBar
        activeFilterId={statusFilter}
        filters={STATUS_FILTERS}
        onChange={(value) => setStatusFilter(value as StatusFilter)}
      />

      <div className="case-layout">
        <Card>
          <div className="metric-stack">
            <strong>Case queue</strong>
            {visibleCases.map((caseItem) => (
              <button
                className={activeCaseId === caseItem.id ? 'page-list-item page-list-item--active' : 'page-list-item'}
                key={caseItem.id}
                onClick={() => {
                  setSelectedCaseId(caseItem.id)
                  const nextSearchParams = new URLSearchParams(searchParams)
                  nextSearchParams.set('case', caseItem.id)
                  setSearchParams(nextSearchParams, { preventScrollReset: true })
                }}
                type="button"
              >
                <strong>{caseItem.title}</strong>
                <span className="metric-row__label">
                  {caseItem.status} · {caseItem.priority}
                </span>
              </button>
            ))}
            {visibleCases.length === 0 ? (
              <EmptyState description="No cases match the current filter." title="Empty queue" />
            ) : null}
            {unpromotedAlerts.map((alert) => (
              <button
                className="page-button"
                disabled={promoteMutation.isPending}
                key={alert.id}
                onClick={() =>
                  promoteMutation.mutate(
                    { alert_id: alert.id },
                    {
                      onSuccess: (detail) => {
                        setSelectedCaseId(detail.case.id)
                        const nextSearchParams = new URLSearchParams(searchParams)
                        nextSearchParams.set('case', detail.case.id)
                        setSearchParams(nextSearchParams, { preventScrollReset: true })
                        showToast('success', `Promoted ${alert.entity_label} to a case.`)
                      },
                      onError: () => showToast('error', 'Could not promote the alert.'),
                    },
                  )
                }
                type="button"
              >
                Promote {alert.entity_label} to case
              </button>
            ))}
          </div>
        </Card>

        {caseQuery.data ? (
          <Card>
            <div className="metric-stack">
              <strong>{caseQuery.data.case.title}</strong>
              <div className="alert-row-card__meta">
                <Chip label={caseQuery.data.case.status} tone="info" />
                <Chip label={caseQuery.data.case.priority} tone="warning" />
                {caseQuery.data.case.assignee ? <Chip label={caseQuery.data.case.assignee} tone="default" /> : null}
              </div>
              <div className="page-actions-inline">
                <button
                  aria-label={`Ask AI for ${caseQuery.data.case.title}`}
                  className="page-button page-button--secondary"
                  onClick={() =>
                    navigate(buildRagChatUrl({
                      knowledgeBaseId,
                      source: 'case',
                      caseId: activeCaseId,
                      alertId: caseQuery.data.case.alert_ids[0],
                      evidencePackId: caseQuery.data.case.evidence_pack_id,
                      question: DEFAULT_RISK_QUESTION,
                    }))
                  }
                  type="button"
                >
                  Ask AI
                </button>
                <button className="page-button" onClick={() => handleUpdate('in_review')} type="button">
                  Mark in review
                </button>
                <button className="page-button page-button--secondary" onClick={() => handleUpdate('closed')} type="button">
                  Close case
                </button>
              </div>
              {caseQuery.data.evidence_pack ? (
                <div className="metric-stack">
                  <strong>Evidence</strong>
                  <span className="metric-row__label">{caseQuery.data.evidence_pack.reasoning}</span>
                </div>
              ) : null}
              <div className="metric-stack">
                <strong>Timeline</strong>
                {caseQuery.data.entity_timeline.length > 0 ? (
                  caseQuery.data.entity_timeline.map((event) => (
                    <div className="metric-row metric-row--stacked" key={`${event.label}-${event.occurred_at}`}>
                      <strong>{event.label.replace(/_/g, ' ')}</strong>
                      <span className="metric-row__label">{event.detail}</span>
                    </div>
                  ))
                ) : (
                  <EmptyState description="No timeline events were captured." title="No timeline" />
                )}
              </div>
              <div className="metric-stack">
                <strong>Submit analyst feedback</strong>
                <label className="metric-stack">
                  <span className="metric-row__label">Feedback label</span>
                  <select
                    className="page-input"
                    onChange={(event) =>
                      setFeedbackLabel(event.target.value as CaseFeedbackCreateRequest['label'])
                    }
                    value={feedbackLabel}
                  >
                    <option value="suspicious">suspicious</option>
                    <option value="not_suspicious">not_suspicious</option>
                    <option value="insufficient_evidence">insufficient_evidence</option>
                  </select>
                </label>
                <label className="metric-stack">
                  <span className="metric-row__label">Evidence adequacy</span>
                  <select
                    className="page-input"
                    onChange={(event) =>
                      setEvidenceAdequacy(
                        event.target.value as CaseFeedbackCreateRequest['evidence_adequacy'],
                      )
                    }
                    value={evidenceAdequacy}
                  >
                    <option value="high">high</option>
                    <option value="medium">medium</option>
                    <option value="low">low</option>
                  </select>
                </label>
                <label className="metric-stack">
                  <span className="metric-row__label">Missing evidence</span>
                  <input
                    className="page-input"
                    onChange={(event) => setMissingEvidence(event.target.value)}
                    value={missingEvidence}
                  />
                </label>
                <label className="metric-stack">
                  <span className="metric-row__label">Feedback notes</span>
                  <textarea
                    className="page-textarea"
                    onChange={(event) => setFeedbackNotes(event.target.value)}
                    placeholder="Document the current evidence assessment"
                    value={feedbackNotes}
                  />
                </label>
                <button
                  className="page-button"
                  disabled={feedbackNotes.trim().length === 0}
                  onClick={() => {
                    feedbackMutation.mutate(
                      {
                        label: feedbackLabel,
                        evidence_adequacy: evidenceAdequacy,
                        missing_evidence: missingEvidence
                          .split(',')
                          .map((item) => item.trim())
                          .filter(Boolean),
                        notes: feedbackNotes,
                      },
                      {
                        onSuccess: () => showToast('success', 'Feedback saved.'),
                        onError: () => showToast('error', 'Could not save feedback.'),
                      },
                    )
                    setMissingEvidence('')
                    setFeedbackNotes('')
                  }}
                  type="button"
                >
                  Save feedback
                </button>
              </div>
              <div className="metric-stack">
                <strong>Feedback history</strong>
                {caseQuery.data.feedback_history.length > 0 ? (
                  caseQuery.data.feedback_history.map((feedback) => (
                    <div className="metric-row metric-row--stacked" key={feedback.submitted_at}>
                      <strong>{feedback.label.replace(/_/g, ' ')}</strong>
                      <span className="metric-row__label">Evidence adequacy: {feedback.evidence_adequacy}</span>
                      <span className="metric-row__label">{feedback.notes}</span>
                      {(feedback.missing_evidence ?? []).length > 0 ? (
                        <ul className="metric-row__label">
                          {(feedback.missing_evidence ?? []).map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <EmptyState description="No feedback has been submitted yet." title="Awaiting review" />
                )}
              </div>
            </div>
          </Card>
        ) : (
          <EmptyState description="Select a case to inspect its detail and feedback history." title="No case selected" />
        )}
      </div>
    </section>
  )
}
