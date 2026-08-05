import { useCallback, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import {
  useAcknowledgeAlert,
  useAlerts,
  useAssignAlert,
  useBulkUpdateAlertStatus,
  useUpdateAlertStatus,
  type AlertFeedFilters,
} from '../api/alerts'
import type { AlertListItem, AlertStatus, CaseSummaryResponse, RuntimeEntity } from '../api/contracts'
import type { Entity as ApiEntity } from '../types/api'
import { useAttachAlertToCase, useCases, usePromoteAlertToCase } from '../api/cases'
import { useDomainConfig, useDomainFeatures } from '../api/config'
import { useEvidencePack } from '../api/evidence'
import { useInvestigationNeighborhood } from '../api/investigation'
import { usePolicyItems } from '../api/policy'
import { ConfirmDialog } from '../components/common/ConfirmDialog'
import { showToast } from '../components/common/toastStore'
import { EvidencePackActions } from '../components/investigation/EvidencePackActions'
import { EvidencePackViewer } from '../components/investigation/EvidencePackViewer'
import { policyItemsForTarget } from '../components/investigation/policyTargets'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterGroup } from '../components/ui/FilterGroup'
import { Card } from '../components/ui/Card'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { StatusPill } from '../components/ui/StatusPill'
import { statusToneForValue } from '../components/ui/statusPill'
import { buildRagChatUrl, DEFAULT_RISK_QUESTION } from '../lib/ragContext'
import {
  ALERT_SORTS,
  applyAlertFilters,
  countBy,
  EMPTY_ALERT_FILTERS,
  hasActiveAlertFilters,
  parseAlertFilters,
  serializeAlertFilters,
  summarizeAlertFilters,
  type AlertFilterState,
  type AlertSortId,
} from '../utils/alertFilters'
import { countLabel } from '../utils/countLabel'
import {
  clearSelection,
  describeSelection,
  pruneSelection,
  selectAll,
  toggleSelection,
} from '../utils/alertSelection'
import { absoluteTime, relativeAge } from '../utils/relativeTime'
import { getEntityTitle } from '../utils/domainDisplay'
import { severityTone } from '../utils/severity'
import { flagLabelFor } from '../utils/flagLabel'
import { toSubgraphResult } from '../utils/subgraph'
import { triageNumeralColor } from '../utils/triage'
import './pages.css'

/** Every severity the platform ranks, not the subset the old chip row offered. */
const SEVERITY_OPTIONS = [
  { id: 'critical', label: 'Critical' },
  { id: 'high', label: 'High' },
  { id: 'medium', label: 'Medium' },
  { id: 'low', label: 'Low' },
]

const STATUS_OPTIONS = [
  { id: 'open', label: 'Open' },
  { id: 'acknowledged', label: 'Acknowledged' },
  { id: 'investigating', label: 'Investigating' },
  { id: 'resolved', label: 'Resolved' },
  { id: 'dismissed', label: 'Dismissed' },
]

const SCORE_FRESHNESS_OPTIONS = [
  { id: 'fresh', label: 'Fresh score' },
  { id: 'stale', label: 'Stale score' },
  { id: 'unknown', label: 'Unknown score' },
]

const EVIDENCE_OPTIONS = [
  { id: 'with_evidence', label: 'With evidence' },
  { id: 'without_evidence', label: 'Without evidence' },
]

const ALERT_STATUS_TRANSITIONS: Record<AlertStatus, AlertStatus[]> = {
  open: ['acknowledged', 'dismissed'],
  acknowledged: ['investigating', 'open'],
  investigating: ['resolved', 'dismissed', 'open'],
  resolved: ['open'],
  dismissed: ['open'],
}

type AlertListRow = Omit<AlertListItem, 'tags'> & {
  tags?: string[]
  assignee?: string | null
}

type CaseListRow = Omit<CaseSummaryResponse, 'alert_ids'> & {
  alert_ids?: string[]
}

type QueueAlert = AlertListRow & {
  tags: string[]
  assignee: string | null
  case_id: string | null
  case_state: string | null
  score_freshness: 'fresh' | 'stale' | 'unknown'
}

function investigationCockpitUrl(alert: {
  entity_id: string
  knowledge_base_id: string
  id: string
  evidence_pack_id?: string | null
}) {
  const params = new URLSearchParams({
    kb: alert.knowledge_base_id,
    alert: alert.id,
  })
  if (alert.evidence_pack_id) {
    params.set('evidence', alert.evidence_pack_id)
  }
  return `/investigation/${encodeURIComponent(alert.entity_id)}?${params.toString()}`
}

function queueValueLabel(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function firstCaseByAlertId(cases: readonly CaseListRow[]): Map<string, CaseListRow> {
  const byAlertId = new Map<string, CaseListRow>()
  for (const caseItem of cases) {
    for (const alertId of caseItem.alert_ids ?? []) {
      if (!byAlertId.has(alertId)) {
        byAlertId.set(alertId, caseItem)
      }
    }
  }
  return byAlertId
}

function scoreFreshness(updatedAt: string | undefined, createdAt: string): QueueAlert['score_freshness'] {
  const timestamp = Date.parse(updatedAt || createdAt)
  if (Number.isNaN(timestamp)) return 'unknown'
  const ageMs = Date.now() - timestamp
  if (ageMs < 0) return 'fresh'
  const ageDays = ageMs / (1000 * 60 * 60 * 24)
  return ageDays <= 14 ? 'fresh' : 'stale'
}

function slaLabel(createdAt: string): string {
  const timestamp = Date.parse(createdAt)
  if (Number.isNaN(timestamp)) return 'SLA unknown'
  const ageDays = (Date.now() - timestamp) / (1000 * 60 * 60 * 24)
  if (ageDays >= 7) return 'SLA risk'
  if (ageDays >= 3) return 'SLA watch'
  return 'SLA current'
}

function nextStatusOptions(status: AlertStatus): AlertStatus[] {
  return [status, ...(ALERT_STATUS_TRANSITIONS[status] ?? [])]
}

type GenerationDecisionSummary = {
  id: string
  label: string
  title: string
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function decisionSummary(
  metadata: AlertListRow['generation_metadata'],
  key: 'suppression' | 'deduplication',
  label: string,
): GenerationDecisionSummary | null {
  const entry = objectValue(objectValue(metadata)?.[key])
  if (!entry) return null
  const decision = typeof entry.decision === 'string' ? entry.decision : 'recorded'
  const reason = typeof entry.reason === 'string' ? entry.reason : `${label} decision recorded.`
  const windowSeconds = typeof entry.window_seconds === 'number'
    ? ` Window: ${entry.window_seconds}s.`
    : ''
  return {
    id: key,
    label: `${label} ${decision.toLowerCase()}`,
    title: `${reason}${windowSeconds}`,
  }
}

function generationDecisionSummaries(alert: AlertListRow): GenerationDecisionSummary[] {
  return [
    decisionSummary(alert.generation_metadata, 'suppression', 'Suppression'),
    decisionSummary(alert.generation_metadata, 'deduplication', 'Dedup'),
  ].filter((summary): summary is GenerationDecisionSummary => summary !== null)
}

function enrichQueueAlerts(
  alerts: readonly AlertListRow[],
  cases: readonly CaseListRow[],
): QueueAlert[] {
  const casesByAlertId = firstCaseByAlertId(cases)
  return alerts.map((alert) => {
    const caseItem = casesByAlertId.get(alert.id)
    return {
      ...alert,
      tags: alert.tags ?? [],
      assignee: alert.assignee ?? caseItem?.assignee ?? null,
      case_id: caseItem?.id ?? null,
      case_state: caseItem?.status ?? null,
      score_freshness: scoreFreshness(alert.updated_at, alert.created_at),
    }
  })
}

function backendAlertFilters(
  knowledgeBaseId: string | null,
  filters: AlertFilterState,
): AlertFeedFilters {
  return {
    ...(knowledgeBaseId ? { knowledgeBaseId } : {}),
    ...(filters.statuses.length > 0 ? { statuses: filters.statuses } : {}),
    ...(filters.severities.length > 0 ? { severities: filters.severities } : {}),
    ...(filters.typologies.length > 0 ? { typologies: filters.typologies } : {}),
    ...(filters.from ? { createdFrom: filters.from } : {}),
    ...(filters.to ? { createdTo: filters.to } : {}),
    ...(filters.evidenceAvailability.length > 0
      ? { evidence: filters.evidenceAvailability[0] }
      : {}),
    ...(filters.scoreFreshnesses.length > 0
      ? { freshness: filters.scoreFreshnesses[0] }
      : {}),
  }
}

export function AlertFeedPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [assignmentDrafts, setAssignmentDrafts] = useState<Record<string, string>>({})
  const [promotedAlertIds, setPromotedAlertIds] = useState<Set<string>>(() => new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [pendingBulkAction, setPendingBulkAction] = useState<'acknowledge' | 'status' | null>(null)
  const [bulkStatus, setBulkStatus] = useState<AlertStatus | ''>('')
  const selectedKnowledgeBaseId = searchParams.get('kb')
  const requestedAlertId = searchParams.get('alert')
  const filters = parseAlertFilters(searchParams)
  const alertsQuery = useAlerts(backendAlertFilters(selectedKnowledgeBaseId, filters))
  const casesQuery = useCases(selectedKnowledgeBaseId)
  const acknowledgeMutation = useAcknowledgeAlert()
  const assignMutation = useAssignAlert()
  const bulkStatusMutation = useBulkUpdateAlertStatus()
  const statusMutation = useUpdateAlertStatus()
  const promoteMutation = usePromoteAlertToCase()
  const attachMutation = useAttachAlertToCase(selectedKnowledgeBaseId)
  const domainConfigQuery = useDomainConfig()
  const featuresQuery = useDomainFeatures()
  const policyItemsQuery = usePolicyItems(selectedKnowledgeBaseId)
  const alertItems = alertsQuery.data?.items ?? []
  const queueItems = enrichQueueAlerts(alertItems, casesQuery.data?.items ?? [])
  const durablePromotedAlertIds = new Set(
    casesQuery.data?.items.flatMap((caseItem) => caseItem.alert_ids) ?? [],
  )

  // Resolve the selected alert's evidence pack and graph neighborhood
  // (both KB-scoped). Hooks must run unconditionally, so derive from the
  // (possibly undefined) query data.
  const selectedAlert = alertItems.find((alert) => alert.id === requestedAlertId) ?? null
  const selectedAlertId = selectedAlert?.id ?? null
  const evidenceQuery = useEvidencePack(
    selectedAlert?.evidence_pack_id ?? null,
    selectedAlert?.knowledge_base_id ?? null,
  )
  const neighborhoodQuery = useInvestigationNeighborhood(
    selectedAlert?.knowledge_base_id ?? null,
    selectedAlert?.entity_id ?? null,
    1,
  )
  // Filter state lives in the URL (UXA-401): shareable, and it survives a
  // reload. Only the parameters the model owns are rewritten, so `?kb=` and
  // `?alert=` are preserved.
  const setFilters = (next: AlertFilterState) => {
    const params = new URLSearchParams(searchParams)
    for (const key of [
      'severity',
      'status',
      'typology',
      'assignee',
      'case',
      'freshness',
      'evidence',
      'q',
      'sort',
      'from',
      'to',
    ]) params.delete(key)
    for (const [key, value] of serializeAlertFilters(next)) params.append(key, value)
    setSearchParams(params, { preventScrollReset: true })
  }
  const updateFilters = (patch: Partial<AlertFilterState>) => setFilters({ ...filters, ...patch })
  const toggleFilter = (dimension: 'severities' | 'statuses' | 'typologies', optionId: string) => {
    const current = filters[dimension]
    updateFilters({
      [dimension]: current.includes(optionId)
        ? current.filter((value) => value !== optionId)
        : [...current, optionId],
    })
  }
  const setSingleFilter = (
    dimension: 'assignees' | 'caseStates' | 'scoreFreshnesses' | 'evidenceAvailability',
    value: string,
  ) => updateFilters({ [dimension]: value ? [value] : [] })

  const domainConfig = domainConfigQuery.data ?? null
  // Stable across renders so the force layout is not rebuilt on every paint.
  const labelForNode = useCallback(
    (node: ApiEntity) =>
      domainConfig ? getEntityTitle(node as unknown as RuntimeEntity, domainConfig) : node.id,
    [domainConfig],
  )
  const capabilities = featuresQuery.data?.capabilities
  const policyItems = policyItemsQuery.data?.items ?? []

  const selectEvidenceAlert = (alertId: string) => {
    const nextSearchParams = new URLSearchParams(searchParams)
    if (selectedAlertId === alertId) {
      nextSearchParams.delete('alert')
    } else {
      nextSearchParams.set('alert', alertId)
    }
    setSearchParams(nextSearchParams, { preventScrollReset: true })
  }

  const assignDraftValue = (alert: QueueAlert) =>
    assignmentDrafts[alert.id] ?? alert.assignee ?? ''

  const setAssignmentDraft = (alertId: string, value: string) =>
    setAssignmentDrafts((current) => ({ ...current, [alertId]: value }))

  const assignQueueAlert = (alert: QueueAlert) => {
    const assignee = assignDraftValue(alert).trim()
    assignMutation.mutate({
      alertId: alert.id,
      knowledgeBaseId: alert.knowledge_base_id,
      assignee: assignee || null,
    })
  }

  if (alertsQuery.isLoading) {
    return <LoadingState label="Loading alert feed" />
  }

  if (alertsQuery.isError) {
    return <ErrorState description="The alert feed could not be loaded. Try again, or switch to another knowledge base." />
  }

  if (!alertsQuery.data) {
    return <LoadingState label="Waiting for alert feed data" />
  }

  const alerts = applyAlertFilters(queueItems, filters)
  const severityCounts = countBy(queueItems, (alert) => alert.severity)
  const statusCounts = countBy(queueItems, (alert) => alert.status)
  const typologyCounts = queueItems.reduce<Record<string, number>>((counts, alert) => {
    for (const tag of alert.tags ?? []) {
      counts[tag] = (counts[tag] ?? 0) + 1
    }
    return counts
  }, {})
  const assigneeCounts = countBy(queueItems, (alert) => alert.assignee || 'unassigned')
  const caseStateCounts = countBy(queueItems, (alert) => alert.case_state || 'no_case')
  const freshnessCounts = countBy(queueItems, (alert) => alert.score_freshness)
  const evidenceCounts = countBy(queueItems, (alert) =>
    alert.evidence_pack_id ? 'with_evidence' : 'without_evidence',
  )
  const typologyOptions = Object.keys(typologyCounts).sort()
  const assigneeOptions = Object.keys(assigneeCounts).sort((left, right) =>
    queueValueLabel(left).localeCompare(queueValueLabel(right)),
  )
  const caseStateOptions = Object.keys(caseStateCounts).sort((left, right) =>
    queueValueLabel(left).localeCompare(queueValueLabel(right)),
  )
  const visibleIds = alerts.map((alert) => alert.id)
  // A bulk action must never touch an alert the analyst can no longer see, so
  // the selection is pruned to what the current filter shows (UXA-406).
  const selection = pruneSelection(selectedIds, visibleIds)
  const allVisibleSelected = visibleIds.length > 0 && selection.size === visibleIds.length

  const runBulkAcknowledge = () => {
    // Each alert carries its own KB, so a bulk action stays correctly scoped
    // even when the feed spans knowledge bases.
    const byId = new Map(alertItems.map((alert) => [alert.id, alert]))
    for (const alertId of selection) {
      const alert = byId.get(alertId)
      if (!alert) continue
      acknowledgeMutation.mutate({
        alertId,
        knowledgeBaseId: alert.knowledge_base_id,
      })
    }
    showToast('success', `${describeSelection(selection.size)} — acknowledged.`)
    setSelectedIds(clearSelection())
    setPendingBulkAction(null)
  }

  const runBulkStatusUpdate = () => {
    if (!bulkStatus) return
    const byKnowledgeBase = new Map<string, string[]>()
    const visibleById = new Map(alerts.map((alert) => [alert.id, alert]))
    for (const alertId of selection) {
      const alert = visibleById.get(alertId)
      if (!alert) continue
      const group = byKnowledgeBase.get(alert.knowledge_base_id) ?? []
      group.push(alert.id)
      byKnowledgeBase.set(alert.knowledge_base_id, group)
    }
    for (const [knowledgeBaseId, alertIds] of byKnowledgeBase) {
      bulkStatusMutation.mutate({
        knowledgeBaseId,
        alertIds,
        status: bulkStatus,
        reason: 'Bulk queue update.',
      })
    }
    showToast('success', `${describeSelection(selection.size)} — status update queued.`)
    setBulkStatus('')
    setSelectedIds(clearSelection())
    setPendingBulkAction(null)
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={countLabel(alertsQuery.data.page.total_items, 'alert')} tone="info" />}
        eyebrow="Triage queue"
        subtitle="Work the queue: review what was flagged, acknowledge what you have seen, and promote what needs a case."
        title="Alert Feed"
      />

      <div className="alert-filter-strip">
        <FilterGroup
          label="Severity"
          onToggle={(id) => toggleFilter('severities', id)}
          options={SEVERITY_OPTIONS.map((option) => ({
            ...option,
            count: severityCounts[option.id] ?? 0,
          }))}
          selected={filters.severities}
        />
        <FilterGroup
          label="Status"
          onToggle={(id) => toggleFilter('statuses', id)}
          options={STATUS_OPTIONS.map((option) => ({
            ...option,
            count: statusCounts[option.id] ?? 0,
          }))}
          selected={filters.statuses}
        />
        {typologyOptions.length > 0 ? (
          <FilterGroup
            label="Typology"
            onToggle={(id) => toggleFilter('typologies', id)}
            options={typologyOptions.map((tag) => ({
              id: tag,
              label: queueValueLabel(tag),
              count: typologyCounts[tag] ?? 0,
            }))}
            selected={filters.typologies}
          />
        ) : null}
        <div className="alert-filter-strip__controls">
          <label className="filter-group__label" htmlFor="alert-search">
            Search
          </label>
          <input
            className="page-input--inline"
            id="alert-search"
            onChange={(event) => updateFilters({ search: event.target.value })}
            placeholder="Entity or finding"
            type="search"
            value={filters.search}
          />
          <label className="filter-group__label" htmlFor="alert-from">
            From
          </label>
          <input
            className="page-input--inline"
            id="alert-from"
            onChange={(event) => updateFilters({ from: event.target.value })}
            type="date"
            value={filters.from}
          />
          <label className="filter-group__label" htmlFor="alert-to">
            To
          </label>
          <input
            className="page-input--inline"
            id="alert-to"
            onChange={(event) => updateFilters({ to: event.target.value })}
            type="date"
            value={filters.to}
          />
          <label className="filter-group__label" htmlFor="alert-assignee">
            Assignee
          </label>
          <select
            className="page-input--inline"
            id="alert-assignee"
            onChange={(event) => setSingleFilter('assignees', event.target.value)}
            value={filters.assignees[0] ?? ''}
          >
            <option value="">All</option>
            {assigneeOptions.map((assignee) => (
              <option key={assignee} value={assignee}>
                {`${queueValueLabel(assignee)} (${assigneeCounts[assignee] ?? 0})`}
              </option>
            ))}
          </select>
          <label className="filter-group__label" htmlFor="alert-case-state">
            Case
          </label>
          <select
            className="page-input--inline"
            id="alert-case-state"
            onChange={(event) => setSingleFilter('caseStates', event.target.value)}
            value={filters.caseStates[0] ?? ''}
          >
            <option value="">All</option>
            {caseStateOptions.map((caseState) => (
              <option key={caseState} value={caseState}>
                {`${queueValueLabel(caseState)} (${caseStateCounts[caseState] ?? 0})`}
              </option>
            ))}
          </select>
          <label className="filter-group__label" htmlFor="alert-freshness">
            Freshness
          </label>
          <select
            className="page-input--inline"
            id="alert-freshness"
            onChange={(event) => setSingleFilter('scoreFreshnesses', event.target.value)}
            value={filters.scoreFreshnesses[0] ?? ''}
          >
            <option value="">All</option>
            {SCORE_FRESHNESS_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {`${option.label} (${freshnessCounts[option.id] ?? 0})`}
              </option>
            ))}
          </select>
          <label className="filter-group__label" htmlFor="alert-evidence">
            Evidence
          </label>
          <select
            className="page-input--inline"
            id="alert-evidence"
            onChange={(event) => setSingleFilter('evidenceAvailability', event.target.value)}
            value={filters.evidenceAvailability[0] ?? ''}
          >
            <option value="">All</option>
            {EVIDENCE_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {`${option.label} (${evidenceCounts[option.id] ?? 0})`}
              </option>
            ))}
          </select>
          <label className="filter-group__label" htmlFor="alert-sort">
            Sort
          </label>
          <select
            className="page-input--inline"
            id="alert-sort"
            onChange={(event) => updateFilters({ sort: event.target.value as AlertSortId })}
            value={filters.sort}
          >
            {ALERT_SORTS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="alert-filter-strip__summary">
          <span aria-live="polite">
            {summarizeAlertFilters({
              shown: alerts.length,
              total: alertItems.length,
              filters,
            })}
          </span>
          {hasActiveAlertFilters(filters) ? (
            <button
              className="page-button page-button--sm page-button--secondary"
              onClick={() => setFilters(EMPTY_ALERT_FILTERS)}
              type="button"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      </div>

      <div className="alert-bulk-bar">
        <label className="alert-bulk-bar__select-all">
          <input
            aria-label="Select all alerts in view"
            checked={allVisibleSelected}
            disabled={visibleIds.length === 0}
            onChange={(event) =>
              setSelectedIds(event.target.checked ? selectAll(visibleIds) : clearSelection())
            }
            type="checkbox"
          />
          Select all in view
        </label>
        {selection.size > 0 ? (
          <>
            <span aria-live="polite">{describeSelection(selection.size)}</span>
            <button
              className="page-button page-button--sm page-button--primary"
              onClick={() => setPendingBulkAction('acknowledge')}
              type="button"
            >
              {`Acknowledge ${countLabel(selection.size, 'alert')}`}
            </button>
            <select
              aria-label="Bulk status"
              className="page-input--inline"
              onChange={(event) => setBulkStatus(event.target.value as AlertStatus | '')}
              value={bulkStatus}
            >
              <option value="">Bulk status</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              className="page-button page-button--sm page-button--secondary"
              disabled={!bulkStatus || bulkStatusMutation.isPending}
              onClick={() => setPendingBulkAction('status')}
              type="button"
            >
              {`Update ${countLabel(selection.size, 'alert')}`}
            </button>
            <button
              className="page-button page-button--sm page-button--secondary"
              onClick={() => setSelectedIds(clearSelection())}
              type="button"
            >
              Clear selection
            </button>
          </>
        ) : null}
      </div>

      <ConfirmDialog
        cancelLabel="Cancel"
        confirmLabel="Acknowledge"
        message={`This marks ${countLabel(selection.size, 'alert')} as seen. It cannot be undone from here.`}
        onCancel={() => setPendingBulkAction(null)}
        onConfirm={runBulkAcknowledge}
        open={pendingBulkAction === 'acknowledge'}
        title={`Acknowledge ${countLabel(selection.size, 'alert')}`}
      />
      <ConfirmDialog
        cancelLabel="Cancel"
        confirmLabel="Update status"
        message={`This requests a ${bulkStatus ? queueValueLabel(bulkStatus) : 'status'} transition for ${countLabel(selection.size, 'alert')}. Invalid transitions are skipped by the server.`}
        onCancel={() => setPendingBulkAction(null)}
        onConfirm={runBulkStatusUpdate}
        open={pendingBulkAction === 'status'}
        title={`Update ${countLabel(selection.size, 'alert')}`}
      />

      {alerts.length > 0 ? (
        alerts.map((alert) => {
          const isPromoted =
            promotedAlertIds.has(alert.id) || durablePromotedAlertIds.has(alert.id)
          const generationDecisions = generationDecisionSummaries(alert)

          const hasPolicySignal =
            policyItemsForTarget(policyItems, 'alert', alert.id).length +
              policyItemsForTarget(policyItems, 'entity', alert.entity_id).length >
            0
          const showEvidenceAction = Boolean(capabilities?.explainability) && Boolean(alert.evidence_pack_id)

          return (
            <Card className="alert-row-card" compact key={alert.id}>
              <div className="triage-row">
                <input
                  aria-label={`Select ${alert.title}`}
                  checked={selection.has(alert.id)}
                  className="triage-row__select"
                  onChange={() => setSelectedIds(toggleSelection(selection, alert.id))}
                  type="checkbox"
                />
                {/* One metric, named. The bare numeral was severity-coloured
                    and sized like a risk score, but carried confidence — and
                    the same number appeared again in a bar below (UXA-303). */}
                <div className="triage-row__metric">
                  <div
                    className="triage-row__numeral"
                    data-testid="triage-numeral"
                    style={{ color: triageNumeralColor(alert.severity) }}
                  >
                    {Math.round(alert.confidence * 100)}
                  </div>
                  <div className="triage-row__metric-label">confidence</div>
                </div>
                <div className="metric-stack">
                  <div className="alert-row-card__header">
                    <div className="alert-row-card__header-info">
                      {/* What is wrong leads; who it happened to follows. */}
                      <div className="alert-row-card__title">{alert.title}</div>
                      <div className="alert-row-card__subject">{alert.entity_label}</div>
                      <div className="alert-row-card__eyebrow">
                        <span className="flag-label">
                          {flagLabelFor({ tags: alert.tags, severity: alert.severity })}
                        </span>
                        {/* A triage queue with no alert age is missing its
                            most important sort key (UXA-303). */}
                        <span
                          className="alert-row-card__age"
                          data-testid="alert-age"
                          title={absoluteTime(alert.created_at)}
                        >
                          {relativeAge(alert.created_at)}
                        </span>
                      </div>
                      <div className="alert-row-card__meta">
                        <StatusPill compact context="Alert severity" label={alert.severity} tone={severityTone(alert.severity)} />
                        <StatusPill compact context="Alert status" label={alert.status} tone={statusToneForValue(alert.status)} />
                        <Chip label={alert.assignee || 'Unassigned'} tone="default" />
                        <Chip
                          label={`Case ${alert.case_state ?? 'none'}`}
                          tone={alert.case_state ? 'info' : 'default'}
                        />
                        <StatusPill
                          ariaLabel={`Score freshness: ${alert.score_freshness}`}
                          compact
                          context="Score freshness"
                          label={
                            SCORE_FRESHNESS_OPTIONS.find((option) => option.id === alert.score_freshness)
                              ?.label ?? 'Unknown score'
                          }
                          tone={statusToneForValue(alert.score_freshness)}
                        />
                        <StatusPill compact context="SLA state" label={slaLabel(alert.created_at)} tone="warning" />
                        {capabilities?.explainability && hasPolicySignal ? (
                          <Chip label="policy" tone="warning" />
                        ) : null}
                      </div>
                    </div>
                    <div className="alert-row-card__header-actions">
                      <div className="alert-row-card__triage-controls">
                        <input
                          aria-label={`Assignee for ${alert.entity_label}`}
                          className="page-input--inline"
                          onChange={(event) => setAssignmentDraft(alert.id, event.target.value)}
                          placeholder="Assign"
                          type="text"
                          value={assignDraftValue(alert)}
                        />
                        <button
                          className="page-button page-button--sm page-button--secondary"
                          disabled={assignMutation.isPending}
                          onClick={() => assignQueueAlert(alert)}
                          type="button"
                        >
                          {`Assign ${alert.entity_label}`}
                        </button>
                        <select
                          aria-label={`Status for ${alert.entity_label}`}
                          className="page-input--inline"
                          disabled={statusMutation.isPending}
                          onChange={(event) => {
                            const status = event.target.value as AlertStatus
                            if (status !== alert.status) {
                              statusMutation.mutate({
                                alertId: alert.id,
                                knowledgeBaseId: alert.knowledge_base_id,
                                status,
                                reason: 'Queue status update.',
                              })
                            }
                          }}
                          value={alert.status}
                        >
                          {nextStatusOptions(alert.status).map((status) => (
                            <option key={status} value={status}>
                              {queueValueLabel(status)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <Link
                        aria-label={`Investigate ${alert.entity_label}`}
                        className="page-button page-button--sm page-button--primary"
                        to={investigationCockpitUrl(alert)}
                      >
                        Investigate entity
                      </Link>
                      <button
                        aria-label={`Ask AI for ${alert.entity_label}`}
                        className="page-button page-button--sm page-button--secondary"
                        title={`Opens RAG Chat with this alert and ${alert.entity_label} attached.`}
                        onClick={() =>
                          navigate(buildRagChatUrl({
                            knowledgeBaseId: alert.knowledge_base_id,
                            source: 'alert',
                            alertId: alert.id,
                            entityId: alert.entity_id,
                            evidencePackId: alert.evidence_pack_id,
                            question: DEFAULT_RISK_QUESTION,
                          }))
                        }
                        type="button"
                      >
                        Ask AI
                      </button>
                      {showEvidenceAction ? (
                        <button
                          className="page-button page-button--sm page-button--secondary"
                          onClick={() => selectEvidenceAlert(alert.id)}
                          type="button"
                        >
                          {selectedAlertId === alert.id ? 'Hide evidence' : 'View evidence'}
                        </button>
                      ) : null}
                      <button
                        aria-label={`${isPromoted ? 'Promoted' : 'Promote'} ${alert.entity_label} to case`}
                        className="page-button page-button--sm"
                        disabled={isPromoted || promoteMutation.isPending}
                        onClick={() =>
                          promoteMutation.mutate(
                            { knowledgeBaseId: alert.knowledge_base_id, alertId: alert.id },
                            {
                              onSuccess: (created) => {
                                setPromotedAlertIds((current) => {
                                  const next = new Set(current)
                                  next.add(alert.id)
                                  return next
                                })
                                // Without the link the case the analyst just
                                // created was unreachable from here (UXA-405).
                                showToast(
                                  'success',
                                  `Promoted ${alert.entity_label} to a case.`,
                                  {
                                    label: 'Open case',
                                    to: `/cases?kb=${encodeURIComponent(created.case.knowledge_base_id)}&case=${encodeURIComponent(created.case.id)}`,
                                  },
                                )
                              },
                              onError: () => showToast('error', 'Could not promote the alert.'),
                            },
                          )
                        }
                        type="button"
                      >
                        {isPromoted ? 'Promoted to case' : 'Promote to case'}
                      </button>
                      <button
                        aria-label={alert.status === 'acknowledged' ? 'Acknowledged' : 'Acknowledge'}
                        className="page-button page-button--sm"
                        disabled={alert.status === 'acknowledged' || acknowledgeMutation.isPending}
                        onClick={() =>
                          acknowledgeMutation.mutate({
                            alertId: alert.id,
                            knowledgeBaseId: alert.knowledge_base_id,
                          })
                        }
                        type="button"
                      >
                        {alert.status === 'acknowledged' ? 'Acknowledged' : 'Acknowledge'}
                      </button>
                    </div>
                  </div>
                  <div
                    className="alert-row-card__reasoning"
                    style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  >
                    {alert.reasoning}
                  </div>
                  {generationDecisions.length > 0 ? (
                    <div className="alert-row-card__generation-decisions">
                      {generationDecisions.map((decision) => (
                        <span
                          className="alert-row-card__generation-decision"
                          key={decision.id}
                          title={decision.title}
                        >
                          {decision.label}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {showEvidenceAction ? (
                    <Link
                      aria-label={`Preview evidence for ${alert.entity_label}`}
                      className="alert-row-card__evidence-preview"
                      to={investigationCockpitUrl(alert)}
                    >
                      Evidence preview
                    </Link>
                  ) : null}
                </div>
              </div>
            </Card>
          )
        })
      ) : (
        <EmptyState
          description={
            alertItems.length === 0
              ? 'No alerts are available for this knowledge base yet.'
              : 'No alerts match the current filter.'
          }
          title={alertItems.length === 0 ? 'No alerts in queue' : 'No matching alerts'}
        />
      )}

      {selectedAlert?.evidence_pack_id && capabilities?.explainability ? (
        evidenceQuery.isLoading ? (
          <LoadingState label="Loading evidence pack" />
        ) : evidenceQuery.data ? (
          <EvidencePackViewer
            actions={
              selectedKnowledgeBaseId ? (
                <EvidencePackActions
                  attach={{
                    alertId: selectedAlert.id,
                    cases: casesQuery.data?.items ?? [],
                    isPending: attachMutation.isPending,
                    onAttach: (caseId) =>
                      attachMutation.mutate(
                        { caseId, payload: { alert_id: selectedAlert.id } },
                        {
                          onSuccess: (detail) =>
                            showToast('success', `Attached to ${detail.case.title}.`, {
                              label: 'Open case',
                              to: `/cases?kb=${encodeURIComponent(selectedKnowledgeBaseId)}&case=${encodeURIComponent(detail.case.id)}`,
                            }),
                          onError: () =>
                            showToast('error', 'Could not attach this alert to the case.'),
                        },
                      ),
                  }}
                  evidencePackId={evidenceQuery.data.id}
                  knowledgeBaseId={selectedKnowledgeBaseId}
                />
              ) : null
            }
            pack={evidenceQuery.data}
            knowledgeBaseId={selectedKnowledgeBaseId}
            subgraph={
              neighborhoodQuery.data
                ? toSubgraphResult(neighborhoodQuery.data.entities, neighborhoodQuery.data.relationships)
                : { nodes: [], edges: [] }
            }
            entityTypes={domainConfig ? domainConfig.entities.map((e) => e.name) : []}
            labelFor={labelForNode}
            selectedEntityId={selectedAlert.entity_id}
          />
        ) : (
          <EmptyState
            description="No evidence pack has been generated for this alert yet."
            title="Evidence pending"
          />
        )
      ) : null}
    </section>
  )
}
