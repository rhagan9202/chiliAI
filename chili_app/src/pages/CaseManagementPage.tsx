import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { useAlerts } from '../api/alerts'
import {
  exportCaseDossier,
  useAddCaseFeedback,
  useCase,
  useCaseDossier,
  useCases,
  usePromoteCase,
  useUpdateCase,
} from '../api/cases'
import type {
  CaseDetailResponse,
  CaseDossierResponse,
  CaseFeedbackCreateRequest,
  EvidenceExportFormat,
} from '../api/contracts'
import { showToast } from '../components/common/toastStore'
import { PlaybookBadge } from '../components/playbooks/PlaybookBadge'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterGroup } from '../components/ui/FilterGroup'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { StatusPill } from '../components/ui/StatusPill'
import { priorityToneForValue, statusToneForValue } from '../components/ui/statusPill'
import { useActiveKnowledgeBase } from '../hooks/useActiveKnowledgeBase'
import { useUrlSearchDraft } from '../hooks/useUrlSearchDraft'
import { buildRagChatUrl, DEFAULT_RISK_QUESTION } from '../lib/ragContext'
import { downloadTextFile, EXPORT_MIME_TYPES } from '../utils/downloadFile'
import {
  applyCaseFilters,
  EMPTY_CASE_FILTERS,
  hasActiveCaseFilters,
  parseCaseFilters,
  serializeCaseFilters,
  summarizeCaseFilters,
  type CaseFilterState,
} from '../utils/caseFilters'
import { countBy } from '../utils/alertFilters'
import { countLabel } from '../utils/countLabel'
import './pages.css'

const STATUS_OPTIONS = [
  { id: 'open', label: 'Open' },
  { id: 'in_review', label: 'In review' },
  { id: 'closed', label: 'Closed' },
]

const DOSSIER_EXPORT_FORMATS: EvidenceExportFormat[] = ['markdown', 'json']

const appendIfPresent = (params: URLSearchParams, key: string, value: string | null | undefined) => {
  if (typeof value === 'string' && value.length > 0) {
    params.set(key, value)
  }
}

function buildCaseCockpitUrl(detail: CaseDetailResponse, knowledgeBaseId: string): string | null {
  const alertsById = new Map(detail.alerts.map((alertItem) => [alertItem.id, alertItem]))
  const expectedPrimaryAlertId = detail.case.originating_alert_id ?? detail.case.alert_ids[0] ?? null
  const primaryAlert =
    detail.case.alert_ids
      .map((alertId) => alertsById.get(alertId))
      .find((alertItem) => typeof alertItem?.entity_id === 'string' && alertItem.entity_id.length > 0) ??
    detail.alerts.find((alertItem) => typeof alertItem.entity_id === 'string' && alertItem.entity_id.length > 0)
  const entityId = primaryAlert?.entity_id

  if (!entityId) {
    return null
  }

  const caseLevelEvidencePackId =
    primaryAlert.id === expectedPrimaryAlertId ? (detail.case.evidence_pack_id ?? detail.evidence_pack?.id) : null
  const evidencePackId = caseLevelEvidencePackId ?? primaryAlert.evidence_pack_id

  const params = new URLSearchParams()
  appendIfPresent(params, 'kb', knowledgeBaseId)
  appendIfPresent(params, 'alert', primaryAlert.id)
  appendIfPresent(params, 'case', detail.case.id)
  appendIfPresent(params, 'evidence', evidencePackId)

  const query = params.toString()
  return `/investigation/${encodeURIComponent(entityId)}${query ? `?${query}` : ''}`
}

function exportFormatLabel(format: EvidenceExportFormat): string {
  return format === 'markdown' ? 'Markdown' : 'JSON'
}

function humanizeCaseLabel(label: string): string {
  return label.replace(/[._]/g, ' ')
}

function reasonLabel(count: number): string {
  return `${count} ${count === 1 ? 'reason' : 'reasons'}`
}

function CaseDossierSummary({ dossier }: { dossier: CaseDossierResponse }) {
  return (
    <>
      <div className="metric-stack">
        <strong>Evidence bundle</strong>
        {dossier.evidence_packs.length > 0 ? (
          dossier.evidence_packs.map((pack) => (
            <div className="metric-row metric-row--stacked" key={pack.id}>
              <strong>{pack.id}</strong>
              <span className="metric-row__label">{pack.reasoning}</span>
              {pack.provenance.length > 0 ? (
                <ul className="metric-row__label">
                  {pack.provenance.map((reference) => (
                    <li key={`${reference.reference_type}-${reference.reference_id}`}>
                      {reference.label}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))
        ) : (
          <EmptyState description="No evidence packs are attached to this case." title="No evidence" />
        )}
      </div>

      <div className="metric-stack">
        <strong>Explanation reviews</strong>
        {dossier.explanation_review_summaries.length > 0 ? (
          dossier.explanation_review_summaries.map((summary) => (
            <div className="metric-row metric-row--stacked" key={summary.review_id}>
              <strong>{summary.evidence_pack_id}</strong>
              <span className="metric-row__label">
                {summary.target.target_type}:{summary.target.target_id}
              </span>
              <span className="metric-row__label">{summary.state}</span>
              <span className="metric-row__label">{reasonLabel(summary.reason_count)}</span>
            </div>
          ))
        ) : (
          <EmptyState
            description="No explanation review status has been attached to this dossier."
            title="No explanation reviews"
          />
        )}
      </div>

      <div className="metric-stack">
        <strong>Chronology</strong>
        {dossier.entity_timeline.length > 0 ? (
          dossier.entity_timeline.map((event) => (
            <div className="metric-row metric-row--stacked" key={`${event.label}-${event.occurred_at}`}>
              <strong>{humanizeCaseLabel(event.label)}</strong>
              <span className="metric-row__label">{event.detail}</span>
            </div>
          ))
        ) : (
          <EmptyState description="No chronology has been captured for this case." title="No chronology" />
        )}
      </div>

      <div className="metric-stack">
        <strong>Decisions</strong>
        {dossier.feedback_history.length > 0 ? (
          dossier.feedback_history.map((feedback) => (
            <div className="metric-row metric-row--stacked" key={feedback.submitted_at}>
              <strong>{humanizeCaseLabel(feedback.label)}</strong>
              <span className="metric-row__label">Evidence adequacy: {feedback.evidence_adequacy}</span>
              <span className="metric-row__label">{feedback.notes}</span>
            </div>
          ))
        ) : (
          <EmptyState description="No analyst decisions are attached to this dossier." title="No decisions" />
        )}
      </div>

      <div className="metric-stack">
        <strong>Audit trail</strong>
        {dossier.audit_events.length > 0 ? (
          dossier.audit_events.map((event) => (
            <div className="metric-row metric-row--stacked" key={event.event_id}>
              <strong>{humanizeCaseLabel(event.action)}</strong>
              <span className="metric-row__label">{event.actor_email ?? event.actor_user_id}</span>
              <span className="metric-row__label">
                {new Date(event.occurred_at).toLocaleString()} · {event.outcome}
              </span>
            </div>
          ))
        ) : (
          <EmptyState description="No audit events are attached to this dossier." title="No audit events" />
        )}
      </div>
    </>
  )
}

export function CaseManagementPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const {
    activeKnowledgeBaseId: knowledgeBaseId,
    isLoading: knowledgeBasesLoading,
    isError: knowledgeBasesError,
  } = useActiveKnowledgeBase()
  const requestedCaseId = searchParams.get('case')
  // URL-backed so a case view is shareable and survives a reload (UXA-401).
  // `replace` because a filter is a view state, not a destination: pushing would
  // make the back button walk through every toggle instead of leaving the page.
  const filters = parseCaseFilters(searchParams)
  const setFilters = (next: CaseFilterState) => {
    const params = new URLSearchParams(searchParams)
    for (const key of ['status', 'q']) params.delete(key)
    for (const [key, value] of serializeCaseFilters(next)) params.append(key, value)
    setSearchParams(params, { preventScrollReset: true, replace: true })
  }
  // No delay: this list is filtered in the browser, so the URL write costs
  // nothing. The draft is still local — see the hook for why.
  const [searchDraft, setSearchDraft] = useUrlSearchDraft(filters.search, (next) =>
    setFilters({ ...parseCaseFilters(searchParams), search: next }),
  )
  const toggleStatus = (optionId: string) =>
    setFilters({
      ...filters,
      statuses: filters.statuses.includes(optionId)
        ? filters.statuses.filter((value) => value !== optionId)
        : [...filters.statuses, optionId],
    })

  const casesQuery = useCases(knowledgeBaseId)
  const alertsQuery = useAlerts({ knowledgeBaseId: knowledgeBaseId ?? undefined })
  const promoteMutation = usePromoteCase(knowledgeBaseId)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const activeCaseId = casesQuery.data?.items.some((caseItem) => caseItem.id === requestedCaseId)
    ? requestedCaseId
    : selectedCaseId ?? casesQuery.data?.items[0]?.id ?? null
  const caseQuery = useCase(knowledgeBaseId, activeCaseId)
  const dossierQuery = useCaseDossier(knowledgeBaseId, activeCaseId)
  const updateCaseMutation = useUpdateCase(knowledgeBaseId, activeCaseId)
  const feedbackMutation = useAddCaseFeedback(knowledgeBaseId, activeCaseId)
  const [dossierExporting, setDossierExporting] = useState<EvidenceExportFormat | null>(null)
  const [feedbackLabel, setFeedbackLabel] = useState<CaseFeedbackCreateRequest['label']>('suspicious')
  const [evidenceAdequacy, setEvidenceAdequacy] =
    useState<CaseFeedbackCreateRequest['evidence_adequacy']>('high')
  const [missingEvidence, setMissingEvidence] = useState('')
  const [feedbackNotes, setFeedbackNotes] = useState('')

  if (knowledgeBasesLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesError) {
    return <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
  }

  if (!knowledgeBaseId) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Investigations"
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
    return <ErrorState description="The case queue could not be loaded. Try again in a moment." />
  }

  if (!casesQuery.data || !alertsQuery.data) {
    return <LoadingState label="Waiting for case data" />
  }

  const visibleCases = applyCaseFilters(casesQuery.data.items, filters)
  const statusCounts = countBy(casesQuery.data.items, (caseItem) => caseItem.status)

  const unpromotedAlerts = alertsQuery.data.items.filter(
    (alert) => !casesQuery.data.items.some((existingCase) => existingCase.alert_ids.includes(alert.id)),
  )
  const caseCockpitUrl = caseQuery.data ? buildCaseCockpitUrl(caseQuery.data, knowledgeBaseId) : null

  const handleUpdate = (status: 'in_review' | 'closed') => {
    updateCaseMutation.mutate(
      { status },
      {
        onSuccess: () => showToast('success', `Case marked ${status.replace(/_/g, ' ')}.`),
        onError: () => showToast('error', 'Could not update the case.'),
      },
    )
  }

  const handleDossierExport = async (format: EvidenceExportFormat) => {
    if (!knowledgeBaseId || !activeCaseId) {
      return
    }
    setDossierExporting(format)
    try {
      const payload = await exportCaseDossier(knowledgeBaseId, activeCaseId, format)
      downloadTextFile(payload.filename, payload.content, EXPORT_MIME_TYPES[payload.format])
    } catch {
      showToast('error', 'Could not export the case dossier.')
    } finally {
      setDossierExporting(null)
    }
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={countLabel(casesQuery.data.page.total_items, 'case')} tone="info" />}
        eyebrow="Investigations"
        subtitle="Track what you are investigating. Promote an alert to open a case with its evidence attached, then record what you found."
        title="Case Management"
      />

      <div className="alert-filter-strip">
        <FilterGroup
          label="Status"
          onToggle={toggleStatus}
          options={STATUS_OPTIONS.map((option) => ({
            ...option,
            count: statusCounts[option.id] ?? 0,
          }))}
          selected={filters.statuses}
        />
        <div className="alert-filter-strip__controls">
          <label className="filter-group__label" htmlFor="case-search">
            Search
          </label>
          <input
            className="page-input--inline"
            id="case-search"
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Case title"
            type="search"
            value={searchDraft}
          />
        </div>
        <div className="alert-filter-strip__summary">
          <span aria-live="polite">
            {summarizeCaseFilters({
              shown: visibleCases.length,
              total: casesQuery.data.items.length,
              filters,
            })}
          </span>
          {hasActiveCaseFilters(filters) ? (
            <button
              className="page-button page-button--sm page-button--secondary"
              onClick={() => setFilters(EMPTY_CASE_FILTERS)}
              type="button"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      </div>

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
                <span className="case-status-strip">
                  <StatusPill compact context="Case status" label={caseItem.status} tone={statusToneForValue(caseItem.status)} />
                  <StatusPill compact context="Case priority" label={caseItem.priority} tone={priorityToneForValue(caseItem.priority)} />
                </span>
              </button>
            ))}
            {visibleCases.length === 0 ? (
              // "Filtered to nothing" and "nothing here yet" are different
              // problems and need different next steps (UXA-305).
              casesQuery.data.items.length > 0 ? (
                <EmptyState
                  action={
                    <button
                      className="page-button page-button--sm"
                      onClick={() => setFilters(EMPTY_CASE_FILTERS)}
                      type="button"
                    >
                      Clear filter
                    </button>
                  }
                  description="No cases match the filters you have set. Clear them to see the rest of the queue."
                  title="No cases match this filter"
                />
              ) : (
                <EmptyState
                  action={
                    <Link
                      className="page-button page-button--sm page-button--primary"
                      to={`/alerts?kb=${encodeURIComponent(knowledgeBaseId)}`}
                    >
                      Go to the Alert Feed
                    </Link>
                  }
                  description="Cases start life as alerts. Promote one from the queue to open your first case here."
                  title="No cases yet"
                />
              )
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
                <StatusPill context="Case status" label={caseQuery.data.case.status} tone={statusToneForValue(caseQuery.data.case.status)} />
                <StatusPill context="Case priority" label={caseQuery.data.case.priority} tone={priorityToneForValue(caseQuery.data.case.priority)} />
                {caseQuery.data.case.assignee ? <Chip label={caseQuery.data.case.assignee} tone="default" /> : null}
              </div>
              {caseQuery.data.case.playbook_ref ? (
                <PlaybookBadge
                  title={caseQuery.data.case.playbook_ref.title}
                  version={caseQuery.data.case.playbook_ref.playbook_version}
                />
              ) : null}
              <div className="page-actions-inline">
                {caseCockpitUrl ? (
                  <Link className="page-button page-button--secondary" to={caseCockpitUrl}>
                    Open cockpit
                  </Link>
                ) : null}
                <button
                  aria-label={`Ask AI for ${caseQuery.data.case.title}`}
                  title={`Opens RAG Chat with this case and its evidence attached.`}
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
              <section aria-label="Case dossier" className="metric-stack">
                <div className="page-actions-inline">
                  <strong>Case dossier</strong>
                  {(dossierQuery.data?.export.formats ?? DOSSIER_EXPORT_FORMATS).map((format) => (
                    <button
                      className={format === 'markdown' ? 'page-button' : 'page-button page-button--secondary'}
                      disabled={dossierExporting !== null}
                      key={format}
                      onClick={() => void handleDossierExport(format)}
                      type="button"
                    >
                      {dossierExporting === format
                        ? 'Exporting...'
                        : `Export dossier ${exportFormatLabel(format)}`}
                    </button>
                  ))}
                </div>
                {dossierQuery.isLoading ? (
                  <span className="metric-row__label">Loading case dossier</span>
                ) : dossierQuery.isError ? (
                  <span className="metric-row__label">Case dossier could not be loaded.</span>
                ) : dossierQuery.data ? (
                  <CaseDossierSummary dossier={dossierQuery.data} />
                ) : (
                  <span className="metric-row__label">Case dossier is not available.</span>
                )}
              </section>
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
