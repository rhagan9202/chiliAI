import { useDomainConfig } from '../api/config'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function ConfigurationPage() {
  const domainConfig = useDomainConfig()
  const entityCount = domainConfig.data?.entities.length ?? 0
  const relationshipCount = domainConfig.data?.relationships.length ?? 0

  if (domainConfig.isLoading) {
    return <LoadingState label="Loading domain configuration" />
  }

  if (domainConfig.isError) {
    return (
      <ErrorState
        description="The configuration endpoint is not available yet. Once the backend is running, this page will render entity, relationship, capability, and UI metadata tables."
      />
    )
  }

  return (
    <section className="page-grid">
      <SectionHeader
        eyebrow="Domain configuration"
        subtitle="This page now uses the shared loading, error, card, and section primitives that future schema-driven configuration views will build on."
        title="Configuration"
      />
      <div className="dashboard-panels">
        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <span className="metric-row__label">Entities loaded</span>
              <strong>{entityCount}</strong>
            </div>
            <div className="metric-row">
              <span className="metric-row__label">Relationships loaded</span>
              <strong>{relationshipCount}</strong>
            </div>
            <div className="metric-row">
              <span className="metric-row__label">Domain</span>
              <strong>{domainConfig.data?.domain.display_name}</strong>
            </div>
          </div>
        </Card>
        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <span className="metric-row__label">Timeseries</span>
              <strong>{domainConfig.data?.capabilities.timeseries ? 'Enabled' : 'Disabled'}</strong>
            </div>
            <div className="metric-row">
              <span className="metric-row__label">GNN</span>
              <strong>{domainConfig.data?.capabilities.gnn ? 'Enabled' : 'Disabled'}</strong>
            </div>
            <div className="metric-row">
              <span className="metric-row__label">RAG Chat</span>
              <strong>{domainConfig.data?.capabilities.rag_chat ? 'Enabled' : 'Disabled'}</strong>
            </div>
          </div>
        </Card>
      </div>
    </section>
  )
}