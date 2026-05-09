import { useState } from 'react'

import { useAlerts } from '../api/alerts'
import { useAddCaseFeedback, useCase, useCases, useCreateCase, useUpdateCase } from '../api/cases'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function CaseManagementPage() {
  const casesQuery = useCases()
  const alertsQuery = useAlerts()
  const createCaseMutation = useCreateCase()
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const activeCaseId = selectedCaseId ?? casesQuery.data?.items[0]?.id ?? null
  const caseQuery = useCase(activeCaseId)
  const updateCaseMutation = useUpdateCase(activeCaseId)
  const feedbackMutation = useAddCaseFeedback(activeCaseId)
  const [feedbackNotes, setFeedbackNotes] = useState('')

  if (casesQuery.isLoading || alertsQuery.isLoading) {
    return <LoadingState label="Loading case queue" />
  }

  if (casesQuery.isError || alertsQuery.isError) {
    return <ErrorState description="Case management data could not be loaded from the backend." />
  }

  if (!casesQuery.data || !alertsQuery.data) {
    return <LoadingState label="Waiting for case data" />
  }

  const unassignedAlert = alertsQuery.data.items.find(
    (alert) => !casesQuery.data.items.some((existingCase) => existingCase.alert_ids.includes(alert.id)),
  )

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${casesQuery.data.page.total_items} cases`} tone="info" />}
        eyebrow="Human feedback loop"
        subtitle="Cases, status updates, and analyst feedback now persist through the backend case endpoints."
        title="Case Management"
      />

      <div className="case-layout">
        <Card>
          <div className="metric-stack">
            <strong>Case queue</strong>
            {casesQuery.data.items.map((caseItem) => (
              <button
                className={selectedCaseId === caseItem.id ? 'page-list-item page-list-item--active' : 'page-list-item'}
                key={caseItem.id}
                onClick={() => setSelectedCaseId(caseItem.id)}
                type="button"
              >
                <strong>{caseItem.title}</strong>
                <span className="metric-row__label">{caseItem.status}</span>
              </button>
            ))}
            {unassignedAlert ? (
              <button
                className="page-button"
                onClick={() =>
                  createCaseMutation.mutate({
                    title: `${unassignedAlert.entity_label} review`,
                    priority: unassignedAlert.severity === 'critical' ? 'critical' : 'high',
                    assignee: 'Unassigned',
                    alert_ids: [unassignedAlert.id],
                  })
                }
                type="button"
              >
                Create case from {unassignedAlert.entity_label}
              </button>
            ) : null}
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
                <button className="page-button" onClick={() => updateCaseMutation.mutate({ status: 'in_review' })} type="button">
                  Mark in review
                </button>
                <button className="page-button page-button--secondary" onClick={() => updateCaseMutation.mutate({ status: 'closed' })} type="button">
                  Close case
                </button>
              </div>
              <div className="metric-stack">
                <strong>Attached alerts</strong>
                {caseQuery.data.alerts.map((alert) => (
                  <div className="metric-row metric-row--stacked" key={alert.id}>
                    <strong>{alert.entity_label}</strong>
                    <span className="metric-row__label">{alert.reasoning}</span>
                  </div>
                ))}
              </div>
              <div className="metric-stack">
                <strong>Submit analyst feedback</strong>
                <textarea
                  className="page-textarea"
                  onChange={(event) => setFeedbackNotes(event.target.value)}
                  placeholder="Document the current evidence assessment"
                  value={feedbackNotes}
                />
                <button
                  className="page-button"
                  disabled={feedbackNotes.trim().length === 0}
                  onClick={() => {
                    feedbackMutation.mutate({
                      label: 'suspicious',
                      evidence_adequacy: 'high',
                      missing_evidence: [],
                      notes: feedbackNotes,
                    })
                    setFeedbackNotes('')
                  }}
                  type="button"
                >
                  Save suspicious finding
                </button>
              </div>
              <div className="metric-stack">
                <strong>Feedback history</strong>
                {caseQuery.data.feedback_history.length > 0 ? (
                  caseQuery.data.feedback_history.map((feedback) => (
                    <div className="metric-row metric-row--stacked" key={feedback.submitted_at}>
                      <strong>{feedback.label.replace(/_/g, ' ')}</strong>
                      <span className="metric-row__label">{feedback.notes}</span>
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