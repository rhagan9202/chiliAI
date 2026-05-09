import { useState } from 'react'

import { useAcknowledgeAlert, useAlerts } from '../api/alerts'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterBar } from '../components/ui/FilterBar'
import { Card } from '../components/ui/Card'
import { LoadingState } from '../components/ui/LoadingState'
import { RiskBadge } from '../components/ui/RiskBadge'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

const filters = [
  { id: 'all', label: 'All' },
  { id: 'critical', label: 'Critical' },
  { id: 'high', label: 'High' },
  { id: 'acknowledged', label: 'Acknowledged' },
]

export function AlertFeedPage() {
  const [activeFilterId, setActiveFilterId] = useState('all')
  const alertsQuery = useAlerts()
  const acknowledgeMutation = useAcknowledgeAlert()

  if (alertsQuery.isLoading) {
    return <LoadingState label="Loading alert feed" />
  }

  if (alertsQuery.isError) {
    return <ErrorState description="The alert feed could not be loaded from the backend." />
  }

  if (!alertsQuery.data) {
    return <LoadingState label="Waiting for alert feed data" />
  }

  const alerts = alertsQuery.data.items.filter((alert) => {
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
        alerts.map((alert) => (
          <Card className="alert-row-card" compact key={alert.id}>
            <div className="alert-row-card__header">
              <div>
                <div className="alert-row-card__title">{alert.entity_label}</div>
                <div className="alert-row-card__subtitle">{alert.reasoning}</div>
              </div>
              <RiskBadge score={Math.round(alert.confidence * 100)} />
            </div>
            <div className="alert-row-card__meta">
              <Chip label={alert.severity} tone={alert.severity === 'critical' ? 'danger' : 'warning'} />
              <Chip label={alert.status} tone={alert.status === 'acknowledged' ? 'success' : 'info'} />
              {alert.tags.map((tag) => (
                <Chip key={tag} label={tag.replace(/-/g, ' ')} tone="default" />
              ))}
            </div>
            <ConfidenceBar value={Math.round(alert.confidence * 100)} />
            <div className="page-actions-inline">
              <button
                className="page-button"
                disabled={alert.status === 'acknowledged' || acknowledgeMutation.isPending}
                onClick={() => acknowledgeMutation.mutate(alert.id)}
                type="button"
              >
                {alert.status === 'acknowledged' ? 'Acknowledged' : 'Acknowledge'}
              </button>
            </div>
          </Card>
        ))
      ) : (
        <EmptyState description="No alerts match the current filter." title="No matching alerts" />
      )}
    </section>
  )
}