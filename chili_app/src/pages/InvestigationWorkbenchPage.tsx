import { useMemo } from 'react'
import { useParams } from 'react-router-dom'

import { useAlerts } from '../api/alerts'
import { useRiskScore, useTimeseries } from '../api/analytics'
import { useEvidencePack } from '../api/evidence'
import { useGraphEntity } from '../api/graph'
import { TrendBars } from '../components/charts/TrendBars'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { RiskBadge } from '../components/ui/RiskBadge'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function InvestigationWorkbenchPage() {
  const { entityId } = useParams()
  const alertsQuery = useAlerts()

  const selectedEntityId = entityId ?? alertsQuery.data?.items[0]?.entity_id ?? null
  const graphQuery = useGraphEntity(selectedEntityId)
  const riskQuery = useRiskScore(selectedEntityId)
  const timeseriesQuery = useTimeseries(selectedEntityId)

  const selectedAlert = useMemo(
    () => alertsQuery.data?.items.find((alert) => alert.entity_id === selectedEntityId) ?? null,
    [alertsQuery.data?.items, selectedEntityId],
  )
  const evidenceQuery = useEvidencePack(selectedAlert?.evidence_pack_id ?? null)

  if (alertsQuery.isLoading || graphQuery.isLoading || riskQuery.isLoading || timeseriesQuery.isLoading) {
    return <LoadingState label="Loading investigation context" />
  }

  if (alertsQuery.isError || graphQuery.isError || riskQuery.isError || timeseriesQuery.isError) {
    return <ErrorState description="Investigation data could not be loaded from the backend." />
  }

  if (!alertsQuery.data || !graphQuery.data || !riskQuery.data || !timeseriesQuery.data) {
    return <LoadingState label="Waiting for investigation data" />
  }

  const graphDetail = graphQuery.data
  const riskScore = riskQuery.data
  const timeseries = timeseriesQuery.data

  return (
    <section className="page-grid">
      <SectionHeader
        actions={selectedAlert ? <Chip label={selectedAlert.severity} tone="warning" /> : undefined}
        eyebrow="Entity workbench"
        subtitle="Graph context, risk breakdown, timeseries drift, and evidence pack details are all now sourced from backend APIs."
        title={graphDetail.entity.label}
      />

      <div className="investigation-layout">
        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <span className="metric-row__label">Composite risk</span>
              <RiskBadge score={Math.round(riskScore.overall_score * 100)} />
            </div>
            <ConfidenceBar value={Math.round(riskScore.overall_score * 100)} />
            <div className="alert-row-card__meta">
              {Object.entries(graphDetail.entity.properties).map(([key, value]) => (
                <Chip key={key} label={`${key}: ${String(value)}`} tone="default" />
              ))}
            </div>
            <p className="page-copy-block">{graphDetail.entity.summary}</p>
          </div>
        </Card>

        <Card>
          <div className="metric-stack">
            <strong>Risk factors</strong>
            {riskScore.factors.map((factor) => (
              <div className="metric-row metric-row--stacked" key={factor.factor_name}>
                <strong>{factor.factor_name.replace(/_/g, ' ')}</strong>
                <span className="metric-row__label">{factor.rationale ?? 'No rationale provided.'}</span>
                <ConfidenceBar value={Math.round(factor.contribution * 100)} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="dashboard-panels">
        <ChartFrameInvestigation timeseries={timeseries.points} />

        <Card>
          <div className="metric-stack">
            <strong>Graph neighborhood</strong>
            {graphDetail.neighbors.map((neighbor) => (
              <div className="metric-row metric-row--stacked" key={neighbor.id}>
                <strong>{neighbor.label}</strong>
                <span className="metric-row__label">{neighbor.summary}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {evidenceQuery.data ? (
        <Card>
          <div className="metric-stack">
            <strong>Evidence pack</strong>
            <p className="page-copy-block">{evidenceQuery.data.reasoning}</p>
            {evidenceQuery.data.items.map((item) => (
              <div className="metric-row metric-row--stacked" key={item.source_id}>
                <strong>{item.source_type}</strong>
                <span className="metric-row__label">{item.quote}</span>
                <span className="metric-row__label">{item.rationale}</span>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </section>
  )
}

function ChartFrameInvestigation({
  timeseries,
}: {
  timeseries: { label: string; value: number; is_anomaly: boolean }[]
}) {
  return (
    <Card>
      <div className="metric-stack">
        <strong>Risk pressure trend</strong>
        <div className="chart-shell">
          <TrendBars
            color="#00d4ff"
            data={timeseries.map((point) => ({ label: point.label, value: Number(point.value.toFixed(2)) }))}
          />
        </div>
        <div className="alert-row-card__meta">
          {timeseries.filter((point) => point.is_anomaly).map((point) => (
            <Chip key={point.label} label={`${point.label} anomaly`} tone="danger" />
          ))}
        </div>
      </div>
    </Card>
  )
}