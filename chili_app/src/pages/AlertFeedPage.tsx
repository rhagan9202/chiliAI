import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useAcknowledgeAlert, useAlerts } from '../api/alerts'
import { useCases, usePromoteAlertToCase } from '../api/cases'
import { useEvidencePack } from '../api/evidence'
import { showToast } from '../components/common/toastStore'
import { EvidencePackViewer } from '../components/investigation/EvidencePackViewer'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterBar } from '../components/ui/FilterBar'
import { Card } from '../components/ui/Card'
import { LoadingState } from '../components/ui/LoadingState'
import { RiskBadge } from '../components/ui/RiskBadge'
import { SectionHeader } from '../components/ui/SectionHeader'
import { buildRagChatUrl, DEFAULT_RISK_QUESTION } from '../lib/ragContext'
import './pages.css'

const filters = [
  { id: 'all', label: 'All' },
  { id: 'critical', label: 'Critical' },
  { id: 'high', label: 'High' },
  { id: 'acknowledged', label: 'Acknowledged' },
]

export function AlertFeedPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeFilterId, setActiveFilterId] = useState('all')
  const [promotedAlertIds, setPromotedAlertIds] = useState<Set<string>>(() => new Set())
  const selectedKnowledgeBaseId = searchParams.get('kb')
  const requestedAlertId = searchParams.get('alert')
  const alertsQuery = useAlerts({
    knowledgeBaseId: selectedKnowledgeBaseId ?? undefined,
  })
  const casesQuery = useCases(selectedKnowledgeBaseId)
  const acknowledgeMutation = useAcknowledgeAlert()
  const promoteMutation = usePromoteAlertToCase()
  const alertItems = alertsQuery.data?.items ?? []
  const durablePromotedAlertIds = new Set(
    casesQuery.data?.items.flatMap((caseItem) => caseItem.alert_ids) ?? [],
  )

  // Resolve the selected alert's evidence pack (KB-scoped). Hooks must run
  // unconditionally, so derive from the (possibly undefined) query data.
  const selectedAlert = alertItems.find((alert) => alert.id === requestedAlertId) ?? null
  const selectedAlertId = selectedAlert?.id ?? null
  const evidenceQuery = useEvidencePack(
    selectedAlert?.evidence_pack_id ?? null,
    selectedAlert?.knowledge_base_id ?? null,
  )

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
    return <ErrorState description="The alert feed could not be loaded from the backend." />
  }

  if (!alertsQuery.data) {
    return <LoadingState label="Waiting for alert feed data" />
  }

  const alerts = alertItems.filter((alert) => {
    if (activeFilterId === 'all') {
      return true
    }
    if (activeFilterId === 'acknowledged') {
      return alert.status === 'acknowledged'
    }
    return alert.severity === activeFilterId
  })

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${alertsQuery.data.page.total_items} alerts loaded`} tone="info" />}
        eyebrow="Triage queue"
        subtitle="The alert feed now reads live backend alert summaries and supports acknowledgement without leaving the queue."
        title="Alert Feed"
      />

      <FilterBar activeFilterId={activeFilterId} filters={filters} onChange={setActiveFilterId} />

      {alerts.length > 0 ? (
        alerts.map((alert) => {
          const isPromoted =
            promotedAlertIds.has(alert.id) || durablePromotedAlertIds.has(alert.id)

          return (
            <Card className="alert-row-card" compact key={alert.id}>
              <div className="alert-row-card__header">
                <div className="alert-row-card__header-info">
                  <div className="alert-row-card__title">{alert.entity_label}</div>
                  <div className="alert-row-card__meta">
                    <Chip label={alert.severity} tone={alert.severity === 'critical' ? 'danger' : 'warning'} />
                    <Chip label={alert.status} tone={alert.status === 'acknowledged' ? 'success' : 'info'} />
                    {(alert.tags ?? []).map((tag) => (
                      <Chip key={tag} label={tag.replace(/-/g, ' ')} tone="default" />
                    ))}
                  </div>
                </div>
                <div className="alert-row-card__header-actions">
                  <RiskBadge score={Math.round(alert.confidence * 100)} />
                  <Link
                    aria-label={`Investigate ${alert.entity_label}`}
                    className="page-button page-button--sm page-button--secondary"
                    to={`/investigation/${encodeURIComponent(alert.entity_id)}?kb=${encodeURIComponent(alert.knowledge_base_id)}`}
                  >
                    Investigate entity
                  </Link>
                  <button
                    aria-label={`Ask AI for ${alert.entity_label}`}
                    className="page-button page-button--sm page-button--secondary"
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
                  {alert.evidence_pack_id ? (
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
                    {alert.status === 'acknowledged' ? '✓' : 'Ack'}
                  </button>
                </div>
              </div>
              <div className="alert-row-card__reasoning">{alert.reasoning}</div>
              <ConfidenceBar value={Math.round(alert.confidence * 100)} />
            </Card>
          )
        })
      ) : (
        <EmptyState description="No alerts match the current filter." title="No matching alerts" />
      )}

      {selectedAlert?.evidence_pack_id ? (
        evidenceQuery.isLoading ? (
          <LoadingState label="Loading evidence pack" />
        ) : evidenceQuery.data ? (
          <EvidencePackViewer
            pack={evidenceQuery.data}
            subgraph={{ nodes: [], edges: [] }}
            entityTypes={[]}
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
