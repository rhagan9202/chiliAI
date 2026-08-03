import type {
  PeerAnalysisResponse,
  PeerCohortContextResponse,
  PeerMetricComparisonResponse,
} from '../../api/contracts'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'
import './analytics.css'

type PeerComparisonPanelProps = {
  analysis: PeerAnalysisResponse | null
  isError?: boolean
  isLoading?: boolean
}

const numberFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
})

function formatMetricName(metricName: string): string {
  return metricName.replace(/_/g, ' ')
}

function formatNumber(value: number): string {
  return numberFormatter.format(value)
}

function cohortBasis(cohort: PeerCohortContextResponse | null | undefined): string | null {
  const entries = Object.entries(cohort?.group_values ?? {})
  if (entries.length === 0) return null
  return entries.map(([key, value]) => `${formatMetricName(key)}: ${value}`).join(' · ')
}

function confidenceLabel(metric: PeerMetricComparisonResponse): string {
  const reason = metric.confidence_reason
    ? ` · ${formatMetricName(metric.confidence_reason)}`
    : ''
  return `${metric.cohort_size} peers · ${metric.confidence} confidence${reason}`
}

function PeerMetricRow({ metric }: { metric: PeerMetricComparisonResponse }) {
  const basis = cohortBasis(metric.cohort)
  return (
    <article className="peer-comparison__item">
      <div className="peer-comparison__header">
        <div>
          <h3 className="peer-comparison__title">{formatMetricName(metric.metric_name)}</h3>
          <p className="peer-comparison__description">{metric.rationale}</p>
        </div>
        <strong className="peer-comparison__score">z-score {formatNumber(metric.z_score)}</strong>
      </div>

      <div className="peer-comparison__stats" aria-label={`${metric.metric_name} peer statistics`}>
        <span>Entity {formatNumber(metric.entity_value)}</span>
        {metric.distribution ? (
          <>
            <span>Peer median {formatNumber(metric.distribution.p50)}</span>
            <span>Peer p90 {formatNumber(metric.distribution.p90)}</span>
          </>
        ) : (
          <span>Peer distribution pending</span>
        )}
        <span>{formatNumber(metric.percentile)} percentile</span>
      </div>

      <div className="peer-comparison__meta">
        <span>{confidenceLabel(metric)}</span>
        {metric.cohort?.label ? <span>{metric.cohort.label}</span> : null}
        {basis ? <span>{basis}</span> : null}
      </div>
    </article>
  )
}

export function PeerComparisonPanel({
  analysis,
  isError = false,
  isLoading = false,
}: PeerComparisonPanelProps) {
  return (
    <Card>
      <div aria-label="Peer comparisons" className="metric-stack" role="group">
        <strong>Peer comparisons</strong>
        {isLoading ? <LoadingState label="Loading peer comparisons" /> : null}
        {isError ? <ErrorState description="Peer comparisons could not be loaded for this entity." /> : null}
        {!isLoading && !isError && (!analysis || analysis.metrics.length === 0) ? (
          <EmptyState
            description="Peer comparisons appear once cohort statistics have been generated for this entity."
            title="No peer comparisons"
          />
        ) : null}
        {!isLoading && !isError && analysis?.metrics.length ? (
          <div className="peer-comparison">
            {analysis.metrics.map((metric) => (
              <PeerMetricRow
                key={`${metric.metric_name}:${metric.interval_start}:${metric.peer_group_key}`}
                metric={metric}
              />
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  )
}
