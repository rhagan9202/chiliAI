import { useCallback, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { useAcknowledgeAlert, useAlerts } from '../api/alerts'
import type { RuntimeEntity } from '../api/contracts'
import type { Entity as ApiEntity } from '../types/api'
import { useCases, usePromoteAlertToCase } from '../api/cases'
import { useDomainConfig, useDomainFeatures } from '../api/config'
import { useEvidencePack } from '../api/evidence'
import { useInvestigationNeighborhood } from '../api/investigation'
import { usePolicyItems } from '../api/policy'
import { ConfirmDialog } from '../components/common/ConfirmDialog'
import { showToast } from '../components/common/toastStore'
import { EvidencePackViewer } from '../components/investigation/EvidencePackViewer'
import { policyItemsForTarget } from '../components/investigation/policyTargets'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterGroup } from '../components/ui/FilterGroup'
import { Card } from '../components/ui/Card'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
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

export function AlertFeedPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [promotedAlertIds, setPromotedAlertIds] = useState<Set<string>>(() => new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [pendingBulkAction, setPendingBulkAction] = useState<'acknowledge' | null>(null)
  const selectedKnowledgeBaseId = searchParams.get('kb')
  const requestedAlertId = searchParams.get('alert')
  const alertsQuery = useAlerts({
    knowledgeBaseId: selectedKnowledgeBaseId ?? undefined,
  })
  const casesQuery = useCases(selectedKnowledgeBaseId)
  const acknowledgeMutation = useAcknowledgeAlert()
  const promoteMutation = usePromoteAlertToCase()
  const domainConfigQuery = useDomainConfig()
  const featuresQuery = useDomainFeatures()
  const policyItemsQuery = usePolicyItems(selectedKnowledgeBaseId)
  const alertItems = alertsQuery.data?.items ?? []
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
  const filters = parseAlertFilters(searchParams)
  const setFilters = (next: AlertFilterState) => {
    const params = new URLSearchParams(searchParams)
    for (const key of ['severity', 'status', 'q', 'sort', 'from', 'to']) params.delete(key)
    for (const [key, value] of serializeAlertFilters(next)) params.append(key, value)
    setSearchParams(params, { preventScrollReset: true })
  }
  const updateFilters = (patch: Partial<AlertFilterState>) => setFilters({ ...filters, ...patch })
  const toggleFilter = (dimension: 'severities' | 'statuses', optionId: string) => {
    const current = filters[dimension]
    updateFilters({
      [dimension]: current.includes(optionId)
        ? current.filter((value) => value !== optionId)
        : [...current, optionId],
    })
  }

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

  if (alertsQuery.isLoading) {
    return <LoadingState label="Loading alert feed" />
  }

  if (alertsQuery.isError) {
    return <ErrorState description="The alert feed could not be loaded. Try again, or switch to another knowledge base." />
  }

  if (!alertsQuery.data) {
    return <LoadingState label="Waiting for alert feed data" />
  }

  const alerts = applyAlertFilters(alertItems, filters)
  const severityCounts = countBy(alertItems, (alert) => alert.severity)
  const statusCounts = countBy(alertItems, (alert) => alert.status)
  const visibleIds = alerts.map((alert) => alert.id)
  // A bulk action must never touch an alert the analyst can no longer see, so
  // the selection is pruned to what the current filter shows (UXA-406).
  const selection = pruneSelection(selectedIds, visibleIds)
  const allVisibleSelected = visibleIds.length > 0 && selection.size === visibleIds.length

  const runBulkAcknowledge = () => {
    for (const alertId of selection) acknowledgeMutation.mutate(alertId)
    showToast('success', `${describeSelection(selection.size)} — acknowledged.`)
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

      {alerts.length > 0 ? (
        alerts.map((alert) => {
          const isPromoted =
            promotedAlertIds.has(alert.id) || durablePromotedAlertIds.has(alert.id)

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
                        <Chip label={alert.severity} tone={severityTone(alert.severity)} />
                        <Chip label={alert.status} tone={alert.status === 'acknowledged' ? 'success' : 'info'} />
                        {capabilities?.explainability && hasPolicySignal ? (
                          <Chip label="policy" tone="warning" />
                        ) : null}
                      </div>
                    </div>
                    <div className="alert-row-card__header-actions">
                      <Link
                        aria-label={`Investigate ${alert.entity_label}`}
                        className="page-button page-button--sm page-button--primary"
                        to={`/investigation/${encodeURIComponent(alert.entity_id)}?kb=${encodeURIComponent(alert.knowledge_base_id)}`}
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
                              onSuccess: () => {
                                setPromotedAlertIds((current) => {
                                  const next = new Set(current)
                                  next.add(alert.id)
                                  return next
                                })
                                showToast('success', `Promoted ${alert.entity_label} to a case.`)
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
                        onClick={() => acknowledgeMutation.mutate(alert.id)}
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
                </div>
              </div>
            </Card>
          )
        })
      ) : (
        <EmptyState description="No alerts match the current filter." title="No matching alerts" />
      )}

      {selectedAlert?.evidence_pack_id && capabilities?.explainability ? (
        evidenceQuery.isLoading ? (
          <LoadingState label="Loading evidence pack" />
        ) : evidenceQuery.data ? (
          <EvidencePackViewer
            pack={evidenceQuery.data}
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
